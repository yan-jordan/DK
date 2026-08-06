"""Build the serving index from the raw IMDb TSV dumps.

Design in one paragraph
-----------------------
The build is done with DuckDB because it streams and spills to disk, so the
whole thing survives on a laptop with a couple of GB of RAM even though
`title.principals.tsv` is ~90M rows. The *serving* side, however, must not pay
for a query engine on every request, so the build lowers everything into flat
binary files that the API `mmap`s: sorted fixed-width id arrays for lookup by
binary search, an int32 postings list for the co-star inverted index, and
blob+offset pairs for the display strings. Nothing is parsed at request time.

Run:
    python -m app.build_index --download
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import duckdb
import numpy as np

from app import config

# --- constants ---------------------------------------------------------------

FILES = {
    "name.basics": "name.basics.tsv.gz",
    "title.basics": "title.basics.tsv.gz",
    "title.crew": "title.crew.tsv.gz",
    "title.principals": "title.principals.tsv.gz",
}

# 'nm' / 'tt' + digits. Currently max 10 chars; 16 leaves headroom and keeps
# the arrays cache-friendly. Build asserts nothing overflows.
ID_WIDTH = 16
ID_DTYPE = f"S{ID_WIDTH}"

BATCH = 500_000

INDEX_VERSION = 3


# --- download ----------------------------------------------------------------

def download(raw_dir: Path, force: bool = False) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for fname in FILES.values():
        dest = raw_dir / fname
        url = config.IMDB_BASE_URL.rstrip("/") + "/" + fname
        if dest.exists() and not force:
            print(f"[download] {fname}: already present ({dest.stat().st_size/1e6:.0f} MB), skipping")
            continue
        print(f"[download] {fname} <- {url}")
        t0 = time.time()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, length=1 << 20)
        tmp.rename(dest)
        print(f"[download] {fname}: {dest.stat().st_size/1e6:.0f} MB in {time.time()-t0:.0f}s")


# --- small helpers -----------------------------------------------------------

_TICK_EVERY = 2_000_000


def _tick(label: str, n: int) -> None:
    """Progress line every few million rows.

    The build has stretches that run for minutes with nothing to show, which
    is indistinguishable from a hang. Cheap output beats a silent process.
    """
    if n % _TICK_EVERY < BATCH:
        print(f"{label}: {n:,} rows", flush=True)


def _csv(path: Path) -> str:
    """DuckDB read_csv() call for an IMDb TSV.

    IMDb dumps are *not* quoted CSV: titles contain bare double quotes
    (e.g. the film `"Weird Al" Yankovic`). Passing quote='' turns off quote
    handling entirely, otherwise those rows shift columns and the parse
    silently corrupts. nullstr handles the literal \\N marker.
    """
    return (
        f"read_csv('{path.as_posix()}', delim='\\t', header=true, quote='', "
        f"escape='', nullstr='\\N', all_varchar=true, compression='gzip', "
        f"ignore_errors=false)"
    )


def _dump_strings(con, query: str, blob_path: Path, off_path: Path) -> int:
    """Write a single string column as one blob + an int64 offset array.

    Row i of the column is blob[off[i]:off[i+1]] decoded as UTF-8. Keeping the
    text out of the process heap is the point: 11M primary titles would be
    several hundred MB of Python objects, but as a blob the API only touches
    the handful of rows a page actually returns.
    """
    reader = con.execute(query).fetch_record_batch(BATCH)
    offsets = [0]
    total = 0
    n = 0
    with open(blob_path, "wb") as bf:
        while True:
            try:
                batch = reader.read_next_batch()
            except StopIteration:
                break
            vals = batch.column(0).to_pylist()
            chunk = []
            for v in vals:
                b = (v or "").encode("utf-8")
                total += len(b)
                offsets.append(total)
                chunk.append(b)
            bf.write(b"".join(chunk))
            n += len(vals)
            _tick(f"    {blob_path.name}", n)
    np.asarray(offsets, dtype=np.int64).tofile(off_path)
    return n


def _dump_ids(con, query: str, path: Path) -> int:
    """Write a string id column as a fixed-width, sorted byte array.

    The array is sorted because ids are assigned in id order, which lets the
    API resolve nconst -> person_id with np.searchsorted instead of holding a
    14M-entry Python dict.
    """
    reader = con.execute(query).fetch_record_batch(BATCH)
    n = 0
    with open(path, "wb") as f:
        while True:
            try:
                batch = reader.read_next_batch()
            except StopIteration:
                break
            vals = [v or "" for v in batch.column(0).to_pylist()]
            longest = max((len(v) for v in vals), default=0)
            if longest > ID_WIDTH:
                raise ValueError(f"id longer than ID_WIDTH={ID_WIDTH}: {longest}")
            f.write(np.asarray(vals, dtype=ID_DTYPE).tobytes())
            n += len(vals)
            _tick(f"    {path.name}", n)
    return n


def _rm_duckdb(db_path: Path) -> None:
    """Remove a DuckDB database file and its write-ahead log."""
    for p in (db_path, db_path.with_suffix(db_path.suffix + ".wal")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def _alive_sql(alias: str) -> str:
    """SQL predicate for 'this person is still alive'. See README."""
    ref = config.ALIVE_REFERENCE_YEAR
    parts = [f"{alias}.death_year IS NULL"]
    if config.ALIVE_REQUIRE_BIRTH_YEAR:
        parts.append(f"{alias}.birth_year IS NOT NULL")
        parts.append(f"{alias}.birth_year >= {ref - config.ALIVE_MAX_AGE}")
    else:
        parts.append(
            f"({alias}.birth_year IS NULL OR {alias}.birth_year >= {ref - config.ALIVE_MAX_AGE})"
        )
    # Guard against corrupt future birth years (they exist in the dump).
    parts.append(f"({alias}.birth_year IS NULL OR {alias}.birth_year <= {ref})")
    return " AND ".join(parts)


# --- build -------------------------------------------------------------------

def build(raw_dir: Path, index_dir: Path) -> dict:
    t_start = time.time()
    index_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = index_dir / ".build_tmp"
    tmp_dir.mkdir(exist_ok=True)

    for f in FILES.values():
        if not (raw_dir / f).exists():
            raise SystemExit(
                f"missing {raw_dir / f}. Run with --download, or mount the raw files."
            )

    # The DuckDB database is backed by a FILE, not ':memory:'. This matters:
    # with an in-memory database, CREATE TABLE keeps the whole table resident,
    # and memory_limit only bounds intermediate buffers -- so building the
    # 14.5M-row `names` table gets the process OOM-killed on a small machine.
    # With a file-backed database DuckDB pages tables to disk and the limit is
    # actually respected. The file is scratch space and is deleted afterwards.
    db_path = index_dir / "build.duckdb"
    _rm_duckdb(db_path)
    con = duckdb.connect(database=str(db_path))
    con.execute(f"SET memory_limit='{config.BUILD_MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory='{tmp_dir.as_posix()}'")
    # See config.BUILD_MAX_TEMP_SIZE: on a Docker volume DuckDB's free-space
    # probe returns nonsense and every spill fails, so pin the cap by hand.
    con.execute(f"SET max_temp_directory_size='{config.BUILD_MAX_TEMP_SIZE}'")
    con.execute("SET preserve_insertion_order=false")
    if config.BUILD_THREADS:
        con.execute(f"SET threads={config.BUILD_THREADS}")

    free_gb = shutil.disk_usage(index_dir).free / 1e9
    print(
        f"[build] memory_limit={config.BUILD_MEMORY_LIMIT} "
        f"max_temp={config.BUILD_MAX_TEMP_SIZE} free_disk={free_gb:.0f}GB"
    )
    if free_gb < 15:
        print(f"[build] WARNING: only {free_gb:.0f}GB free; the build may run out of space")

    stats: dict = {}

    # -- names ----------------------------------------------------------------
    print("[build] names")
    t0 = time.time()
    con.execute(f"""
        CREATE TABLE names AS
        SELECT
            (row_number() OVER (ORDER BY nconst) - 1)::INTEGER AS person_id,
            nconst,
            primaryName                        AS primary_name,
            TRY_CAST(birthYear AS INTEGER)     AS birth_year,
            TRY_CAST(deathYear AS INTEGER)     AS death_year
        FROM {_csv(raw_dir / FILES['name.basics'])}
    """)
    n_names = con.execute("SELECT count(*) FROM names").fetchone()[0]
    _dump_ids(con, "SELECT nconst FROM names ORDER BY person_id", index_dir / "nconst.bin")
    _dump_strings(
        con,
        "SELECT primary_name FROM names ORDER BY person_id",
        index_dir / "name_blob.bin",
        index_dir / "name_off.bin",
    )
    stats["n_names"] = n_names
    print(f"[build] names: {n_names:,} rows in {time.time()-t0:.0f}s")

    # -- titles ---------------------------------------------------------------
    print("[build] titles")
    t0 = time.time()
    con.execute(f"""
        CREATE TABLE titles AS
        SELECT
            (row_number() OVER (ORDER BY tconst) - 1)::INTEGER AS title_id,
            tconst,
            primaryTitle                    AS primary_title,
            titleType                       AS title_type,
            TRY_CAST(startYear AS INTEGER)  AS start_year
        FROM {_csv(raw_dir / FILES['title.basics'])}
    """)
    n_titles = con.execute("SELECT count(*) FROM titles").fetchone()[0]
    _dump_ids(con, "SELECT tconst FROM titles ORDER BY title_id", index_dir / "tconst.bin")
    _dump_strings(
        con,
        "SELECT primary_title FROM titles ORDER BY title_id",
        index_dir / "title_blob.bin",
        index_dir / "title_off.bin",
    )
    _dump_strings(
        con,
        "SELECT title_type FROM titles ORDER BY title_id",
        index_dir / "type_blob.bin",
        index_dir / "type_off.bin",
    )
    # start_year: int16, -1 == unknown. Years outside int16 are corrupt rows.
    years = con.execute(
        "SELECT coalesce(start_year, -1) AS y FROM titles ORDER BY title_id"
    ).fetchnumpy()
    ycol = np.asarray(years["y"], dtype=np.int64)
    n_bad_year = int(((ycol != -1) & ((ycol < 1800) | (ycol > 2200))).sum())
    ycol = np.where((ycol < -1) | (ycol > 32767), -1, ycol).astype(np.int16)
    ycol.tofile(index_dir / "start_year.bin")
    del years, ycol
    stats["n_titles"] = n_titles
    stats["n_suspicious_start_year"] = n_bad_year
    print(f"[build] titles: {n_titles:,} rows in {time.time()-t0:.0f}s")

    # -- endpoint 1: solo creator, still alive --------------------------------
    print("[build] endpoint 1")
    t0 = time.time()
    crew = _csv(raw_dir / FILES["title.crew"])
    # directors = writers AND no comma  =>  exactly one director, exactly one
    # writer, and they are the same person. See README for why this (strict)
    # reading was chosen over the looser "the sets intersect" reading.
    con.execute(f"""
        CREATE TABLE ep1 AS
        SELECT t.title_id, n.person_id
        FROM {crew} c
        JOIN titles t USING (tconst)
        JOIN names  n ON n.nconst = c.directors
        WHERE c.directors IS NOT NULL
          AND c.writers   IS NOT NULL
          AND c.directors = c.writers
          AND c.directors NOT LIKE '%,%'
          AND {_alive_sql('n')}
        ORDER BY t.title_id
    """)
    ep1 = con.execute("SELECT title_id, person_id FROM ep1 ORDER BY title_id").fetchnumpy()
    ep1_titles = np.asarray(ep1["title_id"], dtype=np.int32)
    ep1_people = np.asarray(ep1["person_id"], dtype=np.int32)
    ep1_titles.tofile(index_dir / "ep1_title_ids.bin")
    ep1_people.tofile(index_dir / "ep1_person_ids.bin")
    stats["ep1_total"] = int(ep1_titles.size)
    stats["ep1_distinct_people"] = int(np.unique(ep1_people).size)
    del ep1, ep1_titles, ep1_people
    print(f"[build] endpoint 1: {stats['ep1_total']:,} titles in {time.time()-t0:.0f}s")

    # Diagnostics that the README quotes, so they are computed here rather than
    # by hand-waving afterwards.
    stats["ep1_solo_pairs_before_alive"] = con.execute(f"""
        SELECT count(*)
        FROM {crew} c JOIN titles t USING (tconst) JOIN names n ON n.nconst = c.directors
        WHERE c.directors IS NOT NULL AND c.writers IS NOT NULL
          AND c.directors = c.writers AND c.directors NOT LIKE '%,%'
    """).fetchone()[0]
    stats["ep1_loose_definition_total"] = con.execute(f"""
        SELECT count(*)
        FROM (
          SELECT DISTINCT c.tconst, d.p AS nconst
          FROM {crew} c,
               UNNEST(str_split(c.directors, ',')) AS d(p),
               UNNEST(str_split(c.writers,   ',')) AS w(p2)
          WHERE c.directors IS NOT NULL AND c.writers IS NOT NULL AND d.p = w.p2
        ) x
        JOIN titles t USING (tconst)
        JOIN names  n USING (nconst)
        WHERE {_alive_sql('n')}
    """).fetchone()[0]

    # -- endpoint 2: co-star inverted index -----------------------------------
    print("[build] endpoint 2 postings")
    t0 = time.time()
    cats = ", ".join(f"'{c}'" for c in config.ACTOR_CATEGORIES)
    principals = _csv(raw_dir / FILES["title.principals"])
    # GROUP BY dedupes: a person can legitimately have two principals rows for
    # the same title (e.g. credited as actor and as self), which would
    # otherwise produce duplicate postings and inflate the intersection.
    con.execute(f"""
        CREATE TABLE princ AS
        SELECT n.person_id, t.title_id
        FROM {principals} p
        JOIN names  n USING (nconst)
        JOIN titles t USING (tconst)
        WHERE p.category IN ({cats})
        GROUP BY 1, 2
    """)
    n_postings = con.execute("SELECT count(*) FROM princ").fetchone()[0]

    counts = np.zeros(n_names, dtype=np.int64)
    reader = con.execute(
        "SELECT person_id, title_id FROM princ ORDER BY person_id, title_id"
    ).fetch_record_batch(BATCH)
    written = 0
    with open(index_dir / "postings.bin", "wb") as f:
        while True:
            try:
                batch = reader.read_next_batch()
            except StopIteration:
                break
            pid = batch.column(0).to_numpy(zero_copy_only=False).astype(np.int64)
            tid = batch.column(1).to_numpy(zero_copy_only=False).astype(np.int32)
            counts += np.bincount(pid, minlength=n_names)
            f.write(tid.tobytes())
            written += tid.size
    assert written == n_postings, (written, n_postings)

    offsets = np.zeros(n_names + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    offsets.tofile(index_dir / "postings_off.bin")
    stats["n_postings"] = int(n_postings)
    stats["n_people_with_credits"] = int((counts > 0).sum())
    stats["max_credits_for_one_person"] = int(counts.max()) if n_names else 0
    del counts, offsets
    print(f"[build] endpoint 2: {n_postings:,} postings in {time.time()-t0:.0f}s")

    # -- meta -----------------------------------------------------------------
    meta = {
        "index_version": INDEX_VERSION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "build_seconds": round(time.time() - t_start, 1),
        "id_width": ID_WIDTH,
        "alive_criterion": {
            "reference_year": config.ALIVE_REFERENCE_YEAR,
            "max_age": config.ALIVE_MAX_AGE,
            "require_birth_year": config.ALIVE_REQUIRE_BIRTH_YEAR,
        },
        "actor_categories": list(config.ACTOR_CATEGORIES),
        "stats": stats,
    }
    (index_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    con.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)
    _rm_duckdb(db_path)  # scratch space; the served index is the .bin files
    print(f"[build] done in {meta['build_seconds']}s -> {index_dir}")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the IMDb serving index.")
    ap.add_argument("--download", action="store_true", help="fetch the dumps first")
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    ap.add_argument("--index-dir", type=Path, default=config.INDEX_DIR)
    args = ap.parse_args(argv)

    if args.download or args.force_download:
        download(args.raw_dir, force=args.force_download)
    meta = build(args.raw_dir, args.index_dir)
    print(json.dumps(meta["stats"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
