"""Unit tests for the parts that are easy to get subtly wrong."""
from __future__ import annotations

import numpy as np
import pytest

from app.index import ImdbIndex


@pytest.fixture(scope="module")
def idx(built_index):
    index_dir, _ = built_index
    return ImdbIndex(index_dir)


def test_person_lookup_roundtrip(idx):
    for nm in ["nm0000001", "nm0000005", "nm0000008"]:
        pid = idx.person_id(nm)
        assert pid is not None
        assert idx.nconst[pid].decode() == nm


def test_person_lookup_misses(idx):
    assert idx.person_id("nm9999999") is None
    assert idx.person_id("") is None
    assert idx.person_id("nm" + "9" * 40) is None  # longer than the id field


def test_intersection_matches_python_sets(idx):
    """The fast paths in co_starring() must agree with the obvious answer."""
    rng = np.random.default_rng(1234)
    for _ in range(300):
        a = np.unique(rng.integers(0, 5000, size=rng.integers(0, 400)).astype(np.int32))
        b = np.unique(rng.integers(0, 5000, size=rng.integers(0, 400)).astype(np.int32))
        expected = sorted(set(a.tolist()) & set(b.tolist()))
        got = _intersect(idx, a, b)
        assert got == expected


def test_intersection_small_vs_huge_path(idx):
    """Exercises the searchsorted branch (b.size > 64 * a.size)."""
    b = np.arange(0, 200_000, 2, dtype=np.int32)
    a = np.array([4, 7, 100, 101, 199_998], dtype=np.int32)
    assert _intersect(idx, a, b) == [4, 100, 199_998]


def test_intersection_disjoint_ranges(idx):
    a = np.arange(0, 100, dtype=np.int32)
    b = np.arange(1000, 1100, dtype=np.int32)
    assert _intersect(idx, a, b) == []


def _intersect(idx, a, b):
    """Call the real intersection logic with arbitrary arrays."""
    import app.index as m

    class Fake(m.ImdbIndex):
        def __init__(self, a, b):
            self._a, self._b = a, b

        def credits(self, pid):
            return self._a if pid == 0 else self._b

    return sorted(Fake(a, b).co_starring(0, 1).tolist())


def test_build_stats_are_self_consistent(built_index):
    _, meta = built_index
    s = meta["stats"]
    assert s["ep1_total"] == 3
    # The looser "director set and writer set merely intersect" reading admits
    # tt0000006 and tt0000007 on top of the strict three.
    assert s["ep1_loose_definition_total"] == 5
    assert s["n_people_with_credits"] == 3  # nm5, nm6, nm7
    assert s["n_titles"] == 9
    assert s["n_names"] == 8


def test_health_and_meta(client):
    h = client.get("/health").json()
    assert h["status"] == "ok"
    m = client.get("/meta").json()
    assert m["alive_criterion"]["reference_year"] == 2026
    assert m["actor_categories"] == ["actor", "actress"]
