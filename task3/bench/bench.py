"""Latency harness for endpoint 2.

Why hand-rolled instead of wrk/hey: the interesting variable is *which actors*
you ask about. A benchmark that hammers one pair measures the CPU cache, not
the service. This picks inputs from the real index across the credit-count
distribution, so the tail includes the genuinely expensive pairs (prolific
actors with tens of thousands of credits).

Usage:
    python -m bench.bench --url http://localhost:8000 --requests 2000
    python -m bench.bench --url http://localhost:8000 --profile heavy
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import statistics
import time
from pathlib import Path

import httpx
import numpy as np


def sample_costar_pairs(raw_dir: Path, n: int, seed: int) -> list[tuple[str, str]]:
    """Pairs of actors who genuinely share at least one title.

    This profile exists because the random-pair profiles are almost entirely
    empty results: two actors drawn at random from 3.7M people have essentially
    zero chance of having worked together, so every request short-circuits on
    the disjoint-range check and the benchmark measures nothing. To exercise the
    actual intersection code we have to feed it pairs that really do intersect.

    title.principals is sorted by tconst, so we can stream it and emit one pair
    per title without holding the file in memory. Reservoir sampling keeps the
    selection unbiased across the whole file rather than favouring old titles.
    """
    rng = random.Random(seed)
    reservoir: list[tuple[str, str]] = []
    seen = 0
    path = raw_dir / "title.principals.tsv.gz"
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        header = f.readline().rstrip("\n").split("\t")
        i_t, i_n, i_c = (header.index(c) for c in ("tconst", "nconst", "category"))
        cur: str | None = None
        actors: list[str] = []

        def flush() -> None:
            nonlocal seen
            if len(actors) < 2:
                return
            a, b = rng.sample(actors, 2)
            seen += 1
            if len(reservoir) < n:
                reservoir.append((a, b))
            else:
                j = rng.randrange(seen)
                if j < n:
                    reservoir[j] = (a, b)

        for line in f:
            row = line.rstrip("\n").split("\t")
            if row[i_c] not in ("actor", "actress"):
                continue
            if row[i_t] != cur:
                flush()
                cur, actors = row[i_t], []
            actors.append(row[i_n])
        flush()
    return reservoir


def pick_actors(index_dir: Path, n: int, profile: str, seed: int) -> list[str]:
    """Sample nconsts from the index, weighted by the chosen profile."""
    off = np.memmap(index_dir / "postings_off.bin", dtype=np.int64, mode="r")
    counts = np.diff(np.asarray(off))
    nconst = np.memmap(index_dir / "nconst.bin", dtype="S16", mode="r")

    has_credits = np.flatnonzero(counts > 0)
    c = counts[has_credits]

    if profile == "heavy":
        # Top 0.1% by credit count -- the worst case for the intersection.
        k = max(int(len(has_credits) * 0.001), 2)
        chosen = has_credits[np.argsort(c)[-k:]]
    elif profile == "typical":
        # Actors with 5..200 credits: what a real query mostly looks like.
        chosen = has_credits[(c >= 5) & (c <= 200)]
        if chosen.size < 2:
            chosen = has_credits
    else:  # mixed
        chosen = has_credits

    rng = np.random.default_rng(seed)
    picks = rng.choice(chosen, size=min(n, chosen.size), replace=chosen.size < n)
    return [nconst[i].decode().strip("\x00") for i in picks]


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def run(
    url: str,
    index_dir: Path,
    n: int,
    warmup: int,
    profile: str,
    seed: int,
    raw_dir: Path | None = None,
) -> dict:
    rng = random.Random(seed)

    if profile == "costars":
        if raw_dir is None:
            raise SystemExit("--raw-dir is required for the 'costars' profile")
        print("  building co-star pair pool (one full pass over principals)...")
        pairs = sample_costar_pairs(raw_dir, max(n * 2, 5000), seed)
        if not pairs:
            raise SystemExit("no co-starring pairs found")

        def a_pair() -> tuple[str, str]:
            return rng.choice(pairs)
    else:
        pool = pick_actors(index_dir, max(n * 2, 1000), profile, seed)

        def a_pair() -> tuple[str, str]:
            while True:
                a, b = rng.choice(pool), rng.choice(pool)
                if a != b:
                    return a, b

    lat: list[float] = []
    totals: list[int] = []
    # Explicit connection reuse -- otherwise we would be timing TCP handshakes.
    with httpx.Client(base_url=url, timeout=30.0) as c:
        for _ in range(warmup):
            a, b = a_pair()
            c.get("/v1/titles/co-starring", params={"actor1": a, "actor2": b})
        for _ in range(n):
            a, b = a_pair()
            t0 = time.perf_counter()
            r = c.get("/v1/titles/co-starring", params={"actor1": a, "actor2": b})
            dt = (time.perf_counter() - t0) * 1000.0
            if r.status_code == 200:
                lat.append(dt)
                totals.append(r.json()["total"])

    nonempty = sum(1 for t in totals if t > 0)
    return {
        "profile": profile,
        "requests": len(lat),
        "p50_ms": round(percentile(lat, 50), 3),
        "p90_ms": round(percentile(lat, 90), 3),
        "p95_ms": round(percentile(lat, 95), 3),
        "p99_ms": round(percentile(lat, 99), 3),
        "max_ms": round(max(lat), 3) if lat else None,
        "mean_ms": round(statistics.fmean(lat), 3) if lat else None,
        "nonempty_results": nonempty,
        # A profile where almost nothing intersects is measuring the empty-set
        # short circuit, not the intersection. Say so in the output instead of
        # letting the reader assume the number means more than it does.
        "measures_real_intersections": nonempty > len(lat) * 0.5,
        "mean_results_when_nonempty": (
            round(sum(totals) / nonempty, 1) if nonempty else 0
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--index-dir", type=Path, default=Path("/data/index"))
    ap.add_argument("--raw-dir", type=Path, default=Path("/data/raw"))
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--profile",
        default="all",
        choices=["all", "costars", "typical", "mixed", "heavy"],
        help=(
            "costars = pairs that really did work together (the headline number); "
            "typical/mixed/heavy = random pairs from slices of the credit-count "
            "distribution, which mostly return empty"
        ),
    )
    args = ap.parse_args()

    profiles = (
        ["costars", "typical", "mixed", "heavy"]
        if args.profile == "all"
        else [args.profile]
    )
    out = []
    for p in profiles:
        print(f"[bench] profile={p}", flush=True)
        out.append(
            run(
                args.url,
                args.index_dir,
                args.requests,
                args.warmup,
                p,
                args.seed,
                args.raw_dir,
            )
        )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
