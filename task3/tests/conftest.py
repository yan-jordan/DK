"""A tiny synthetic IMDb dump with hand-checked expected answers.

The fixture is deliberately full of the nasty cases found in the real dump:
multiple directors, multiple writers, a bare double quote inside a title,
\\N everywhere, a dead person, a person with no birthYear, a person born in
1830 who has no deathYear, and a duplicated principals row.
"""
from __future__ import annotations

import gzip
import importlib
from pathlib import Path

import pytest

NAME_BASICS = [
    # nconst, primaryName, birthYear, deathYear, primaryProfession, knownForTitles
    ("nm0000001", "Alive Auteur", "1970", r"\N", "director,writer", r"\N"),
    ("nm0000002", "Dead Auteur", "1940", "2001", "director,writer", r"\N"),
    ("nm0000003", "Unknown Birth Auteur", r"\N", r"\N", "director,writer", r"\N"),
    ("nm0000004", "Implausibly Old Auteur", "1830", r"\N", "director,writer", r"\N"),
    ("nm0000005", 'Actor "Quotes" One', "1980", r"\N", "actor", r"\N"),
    ("nm0000006", "Actor Two", "1982", r"\N", "actress", r"\N"),
    ("nm0000007", "Actor Three", "1985", r"\N", "actor", r"\N"),
    ("nm0000008", "Co Director", "1975", r"\N", "director", r"\N"),
]

TITLE_BASICS = [
    # tconst, titleType, primaryTitle, originalTitle, isAdult, startYear, endYear, runtime, genres
    ("tt0000001", "movie", "Solo By Living Person", "Solo", "0", "1999", r"\N", "90", "Drama"),
    ("tt0000002", "movie", "Solo By Dead Person", "Solo2", "0", "1980", r"\N", "90", "Drama"),
    ("tt0000003", "movie", "Solo By Unknown Birth", "Solo3", "0", "2001", r"\N", "90", "Drama"),
    ("tt0000004", "movie", "Solo By Very Old Person", "Solo4", "0", "1900", r"\N", "90", "Drama"),
    ("tt0000005", "movie", 'The "Quoted" Film', "Quoted", "0", r"\N", r"\N", "90", "Comedy"),
    ("tt0000006", "movie", "Two Directors One Writer", "TwoDir", "0", "2010", r"\N", "90", "Drama"),
    ("tt0000007", "movie", "One Director Two Writers", "OneDir", "0", "2011", r"\N", "90", "Drama"),
    ("tt0000008", "tvSeries", "Solo Series By Living Person", "SoloS", "0", "2015", r"\N", "45", "Drama"),
    ("tt0000009", "movie", "No Crew At All", "NoCrew", "0", "2020", r"\N", "90", "Drama"),
]

TITLE_CREW = [
    # tconst, directors, writers
    ("tt0000001", "nm0000001", "nm0000001"),          # counts
    ("tt0000002", "nm0000002", "nm0000002"),          # dead -> excluded
    ("tt0000003", "nm0000003", "nm0000003"),          # unknown birth -> excluded
    ("tt0000004", "nm0000004", "nm0000004"),          # born 1830, no death -> excluded
    ("tt0000005", "nm0000001", "nm0000001"),          # counts (quoted title)
    ("tt0000006", "nm0000001,nm0000008", "nm0000001"),  # strict def -> excluded
    ("tt0000007", "nm0000001", "nm0000001,nm0000008"),  # strict def -> excluded
    ("tt0000008", "nm0000001", "nm0000001"),          # counts (tvSeries)
    ("tt0000009", r"\N", r"\N"),                      # excluded
]

TITLE_PRINCIPALS = [
    # tconst, ordering, nconst, category, job, characters
    ("tt0000001", "1", "nm0000005", "actor", r"\N", r"\N"),
    ("tt0000001", "2", "nm0000006", "actress", r"\N", r"\N"),
    ("tt0000001", "3", "nm0000001", "director", r"\N", r"\N"),
    ("tt0000002", "1", "nm0000005", "actor", r"\N", r"\N"),
    ("tt0000002", "2", "nm0000006", "actress", r"\N", r"\N"),
    ("tt0000003", "1", "nm0000005", "actor", r"\N", r"\N"),
    ("tt0000003", "2", "nm0000007", "actor", r"\N", r"\N"),
    # duplicate row for the same (title, person) -- must not double count
    ("tt0000005", "1", "nm0000005", "actor", r"\N", r"\N"),
    ("tt0000005", "2", "nm0000005", "actor", r"\N", r"\N"),
    ("tt0000005", "3", "nm0000006", "actress", r"\N", r"\N"),
    # 'self' is not an acting credit under the default category set
    ("tt0000009", "1", "nm0000005", "self", r"\N", r"\N"),
    ("tt0000009", "2", "nm0000006", "self", r"\N", r"\N"),
]

HEADERS = {
    "name.basics.tsv.gz": "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles",
    "title.basics.tsv.gz": "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres",
    "title.crew.tsv.gz": "tconst\tdirectors\twriters",
    "title.principals.tsv.gz": "tconst\tordering\tnconst\tcategory\tjob\tcharacters",
}
ROWS = {
    "name.basics.tsv.gz": NAME_BASICS,
    "title.basics.tsv.gz": TITLE_BASICS,
    "title.crew.tsv.gz": TITLE_CREW,
    "title.principals.tsv.gz": TITLE_PRINCIPALS,
}


def _write(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for fname, header in HEADERS.items():
        lines = [header] + ["\t".join(r) for r in ROWS[fname]]
        with gzip.open(raw_dir / fname, "wt", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")


@pytest.fixture(scope="session")
def built_index(tmp_path_factory, monkeypatch_session):
    root = tmp_path_factory.mktemp("imdb")
    raw, index = root / "raw", root / "index"
    _write(raw)

    monkeypatch_session.setenv("IMDB_ALIVE_REFERENCE_YEAR", "2026")
    monkeypatch_session.setenv("IMDB_ALIVE_MAX_AGE", "100")
    monkeypatch_session.setenv("IMDB_ALIVE_REQUIRE_BIRTH_YEAR", "1")
    monkeypatch_session.setenv("IMDB_ACTOR_CATEGORIES", "actor,actress")
    monkeypatch_session.setenv("IMDB_RAW_DIR", str(raw))
    monkeypatch_session.setenv("IMDB_INDEX_DIR", str(index))

    from app import config as cfg
    importlib.reload(cfg)
    from app import build_index as bi
    importlib.reload(bi)

    meta = bi.build(raw, index)
    return index, meta


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session")
def client(built_index):
    index_dir, _ = built_index
    import os

    os.environ["IMDB_INDEX_DIR"] = str(index_dir)
    from fastapi.testclient import TestClient
    from app import main as app_main
    import importlib

    importlib.reload(app_main)
    with TestClient(app_main.app) as c:
        yield c
