"""Independent re-computation of the endpoint-1 total, and spot checks for endpoint 2.

The point of this script is that it shares *no code* with the build. The build
uses DuckDB SQL; this streams the gzip files line by line in pure Python and
counts with a dict. If the two disagree, one of them is wrong, and "I ran my
code and it printed a number" is not evidence of anything.

Usage:
    python -m scripts.verify --raw-dir /data/raw --index-dir /data/index
    python -m scripts.verify --raw-dir /data/raw --index-dir /data/index --url http://localhost:8000
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from pathlib import Path


def stream(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        header = f.readline().rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        for line in f:
            yield idx, line.rstrip("\n").split("\t")


def recount_endpoint1(raw_dir: Path, ref_year: int, max_age: int, require_birth: bool):
    """Pure-Python re-derivation of the endpoint-1 result set."""
    alive: set[str] = set()
    n_names = 0
    for idx, row in stream(raw_dir / "name.basics.tsv.gz"):
        n_names += 1
        nconst = row[idx["nconst"]]
        birth = row[idx["birthYear"]]
        death = row[idx["deathYear"]]
        if death != r"\N":
            continue
        if birth == r"\N":
            if require_birth:
                continue
        else:
            try:
                b = int(birth)
            except ValueError:
                continue
            if b < ref_year - max_age or b > ref_year:
                continue
        alive.add(nconst)

    known_titles: set[str] = set()
    for idx, row in stream(raw_dir / "title.basics.tsv.gz"):
        known_titles.add(row[idx["tconst"]])

    strict = 0
    loose = 0
    solo_pairs = 0
    for idx, row in stream(raw_dir / "title.crew.tsv.gz"):
        tconst = row[idx["tconst"]]
        directors = row[idx["directors"]]
        writers = row[idx["writers"]]
        if directors == r"\N" or writers == r"\N":
            continue
        if tconst not in known_titles:
            continue
        if directors == writers and "," not in directors:
            solo_pairs += 1
            if directors in alive:
                strict += 1
        d_set = set(directors.split(","))
        w_set = set(writers.split(","))
        if any(p in alive for p in (d_set & w_set)):
            loose += 1

    return {
        "n_names": n_names,
        "n_alive": len(alive),
        "n_titles": len(known_titles),
        "solo_pairs_before_alive_filter": solo_pairs,
        "strict_total": strict,
        "loose_total": loose,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=Path("/data/raw"))
    ap.add_argument("--index-dir", type=Path, default=Path("/data/index"))
    ap.add_argument("--url", default=None, help="also cross-check the live API")
    ap.add_argument("--spot-checks", type=int, default=20)
    args = ap.parse_args()

    meta = json.loads((args.index_dir / "meta.json").read_text())
    crit = meta["alive_criterion"]
    print("index says:", json.dumps(meta["stats"], indent=2))

    got = recount_endpoint1(
        args.raw_dir,
        crit["reference_year"],
        crit["max_age"],
        crit["require_birth_year"],
    )
    print("independent recount:", json.dumps(got, indent=2))

    ok = True
    checks = [
        ("ep1_total", meta["stats"]["ep1_total"], got["strict_total"]),
        ("n_names", meta["stats"]["n_names"], got["n_names"]),
        ("n_titles", meta["stats"]["n_titles"], got["n_titles"]),
        (
            "ep1_solo_pairs_before_alive",
            meta["stats"]["ep1_solo_pairs_before_alive"],
            got["solo_pairs_before_alive_filter"],
        ),
    ]
    for name, a, b in checks:
        status = "OK " if a == b else "FAIL"
        if a != b:
            ok = False
        print(f"[{status}] {name}: index={a:,} recount={b:,}")

    if args.url:
        import httpx

        with httpx.Client(base_url=args.url, timeout=60) as c:
            api_total = c.get("/v1/titles/solo-creator", params={"pageSize": 1}).json()["total"]
            status = "OK " if api_total == got["strict_total"] else "FAIL"
            if api_total != got["strict_total"]:
                ok = False
            print(f"[{status}] api ep1 total: {api_total:,}")
            ok = _spot_check_endpoint2(c, args.raw_dir, args.index_dir, args.spot_checks) and ok

    return 0 if ok else 1


def _spot_check_endpoint2(client, raw_dir: Path, index_dir: Path, n: int) -> bool:
    """Re-derive a handful of co-star answers straight from principals.

    Order matters here. The obvious implementation -- build a dict of every
    actor to every title they were in, then look pairs up -- needs ~40M Python
    strings held in sets, several GB of heap, to answer 20 questions. Instead we
    choose the people FIRST and then stream the file once, keeping rows only for
    those few nconsts. Memory is then O(credits of 2n people), not O(dataset).
    """
    import numpy as np

    print(f"\nspot-checking endpoint 2 on {n} pairs...")
    rng = random.Random(7)

    off = np.memmap(index_dir / "postings_off.bin", dtype=np.int64, mode="r")
    counts = np.diff(np.asarray(off))
    nconst = np.memmap(index_dir / "nconst.bin", dtype="S16", mode="r")
    eligible = np.flatnonzero(counts >= 3)
    if eligible.size < 2:
        print("[SKIP] not enough people with credits")
        return True

    picks = [int(eligible[rng.randrange(eligible.size)]) for _ in range(2 * n)]
    ids = [nconst[i].decode().strip("\x00") for i in picks]
    pairs = [(ids[i], ids[i + 1]) for i in range(0, len(ids) - 1, 2) if ids[i] != ids[i + 1]]
    wanted = {p for pair in pairs for p in pair}

    titles_of: dict[str, set[str]] = {p: set() for p in wanted}
    for idx, row in stream(raw_dir / "title.principals.tsv.gz"):
        nm = row[idx["nconst"]]
        if nm in titles_of and row[idx["category"]] in ("actor", "actress"):
            titles_of[nm].add(row[idx["tconst"]])

    ok = True
    for a, b in pairs:
        expected = titles_of[a] & titles_of[b]
        r = client.get(
            "/v1/titles/co-starring",
            params={"actor1": a, "actor2": b, "pageSize": 500},
        )
        got = {i["tconst"] for i in r.json().get("items", [])}
        if got != expected:
            ok = False
            print(f"[FAIL] {a} x {b}: api={sorted(got)[:5]} expected={sorted(expected)[:5]}")
    print(
        f"[OK ] endpoint 2: {len(pairs)} pairs re-derived from raw data and matched"
        if ok
        else "[FAIL] endpoint 2 mismatch"
    )
    return ok


if __name__ == "__main__":
    sys.exit(main())
