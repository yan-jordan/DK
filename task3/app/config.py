"""Configuration, read from environment variables.

Everything that a reviewer might want to change without touching code lives here.
"""
from __future__ import annotations

import os
from pathlib import Path

# Where the downloaded .tsv.gz files are cached.
RAW_DIR = Path(os.getenv("IMDB_RAW_DIR", "/data/raw"))

# Where the built index artifacts live.
INDEX_DIR = Path(os.getenv("IMDB_INDEX_DIR", "/data/index"))

IMDB_BASE_URL = os.getenv("IMDB_BASE_URL", "https://datasets.imdbws.com/")

# --- Endpoint 1: the "is this person alive?" criterion -----------------------
# Reference year used for the age cutoff. Pinned via env so that results are
# reproducible: if this floats with the wall clock, the endpoint's total count
# silently changes over time, which makes the README's number unverifiable.
ALIVE_REFERENCE_YEAR = int(os.getenv("IMDB_ALIVE_REFERENCE_YEAR", "2026"))

# A person with no deathYear is only treated as alive if they were born within
# this many years of the reference year. See README for the reasoning.
ALIVE_MAX_AGE = int(os.getenv("IMDB_ALIVE_MAX_AGE", "100"))

# Require a known birthYear to call someone alive. If False, people with an
# unknown birthYear and no deathYear are also counted as alive.
ALIVE_REQUIRE_BIRTH_YEAR = os.getenv("IMDB_ALIVE_REQUIRE_BIRTH_YEAR", "1") == "1"

# --- Endpoint 2 --------------------------------------------------------------
# principals.category values that count as "acted in".
ACTOR_CATEGORIES = tuple(
    c.strip()
    for c in os.getenv("IMDB_ACTOR_CATEGORIES", "actor,actress").split(",")
    if c.strip()
)

# --- API ---------------------------------------------------------------------
DEFAULT_PAGE_SIZE = int(os.getenv("IMDB_DEFAULT_PAGE_SIZE", "50"))
MAX_PAGE_SIZE = int(os.getenv("IMDB_MAX_PAGE_SIZE", "500"))

# DuckDB build-time limits. The build must survive on a laptop, so memory is
# capped and DuckDB is allowed to spill to disk.
BUILD_MEMORY_LIMIT = os.getenv("IMDB_BUILD_MEMORY_LIMIT", "2GB")
BUILD_THREADS = int(os.getenv("IMDB_BUILD_THREADS", "0")) or None

# Cap on DuckDB's spill directory. This MUST be set explicitly: left to its
# default, DuckDB probes the free space of the filesystem holding temp_directory,
# and on a Docker volume (overlay/virtiofs) that probe returns garbage --
# observed reading was "16383.9 PiB used of 400.1 GiB", which makes every spill
# fail immediately. An explicit value bypasses the broken auto-detection.
BUILD_MAX_TEMP_SIZE = os.getenv("IMDB_BUILD_MAX_TEMP_SIZE", "40GiB")
