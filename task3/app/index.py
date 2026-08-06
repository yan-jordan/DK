"""Read-only, memory-mapped view over the built index.

Everything here is immutable after load. That is deliberate: the process holds
no mutable shared state, so N uvicorn workers are N independent readers of the
same page cache, and the OS deduplicates the physical memory between them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class IndexError_(RuntimeError):
    pass


def _mmap(path: Path, dtype) -> np.ndarray:
    """np.memmap refuses zero-length files; degenerate indexes must still load."""
    if path.stat().st_size == 0:
        return np.empty(0, dtype=dtype)
    return np.memmap(path, dtype=dtype, mode="r")


@dataclass(frozen=True)
class Title:
    tconst: str
    primary_title: str
    title_type: str
    start_year: int | None


class Blob:
    """A blob + int64 offsets pair; row i is blob[off[i]:off[i+1]]."""

    __slots__ = ("_blob", "_off")

    def __init__(self, blob_path: Path, off_path: Path):
        self._off = _mmap(off_path, np.int64)
        self._blob = _mmap(blob_path, np.uint8)

    def __len__(self) -> int:
        return max(len(self._off) - 1, 0)

    def get(self, i: int) -> str:
        a, b = int(self._off[i]), int(self._off[i + 1])
        return self._blob[a:b].tobytes().decode("utf-8", errors="replace")


class ImdbIndex:
    def __init__(self, index_dir: Path):
        self.dir = Path(index_dir)
        meta_path = self.dir / "meta.json"
        if not meta_path.exists():
            raise IndexError_(
                f"no index at {self.dir}. Build it with "
                f"`python -m app.build_index --download`."
            )
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        w = self.meta.get("id_width", 16)
        self._id_dtype = np.dtype(f"S{w}")

        d = self.dir
        self.nconst = _mmap(d / "nconst.bin", self._id_dtype)
        self.tconst = _mmap(d / "tconst.bin", self._id_dtype)
        self.names = Blob(d / "name_blob.bin", d / "name_off.bin")
        self.titles = Blob(d / "title_blob.bin", d / "title_off.bin")
        self.types = Blob(d / "type_blob.bin", d / "type_off.bin")
        self.start_year = _mmap(d / "start_year.bin", np.int16)

        self.ep1_title_ids = _mmap(d / "ep1_title_ids.bin", np.int32)
        self.ep1_person_ids = _mmap(d / "ep1_person_ids.bin", np.int32)

        self.postings = _mmap(d / "postings.bin", np.int32)
        self.postings_off = _mmap(d / "postings_off.bin", np.int64)

        if len(self.postings_off) != len(self.nconst) + 1:
            raise IndexError_("index is inconsistent (postings offsets vs names)")

    # -- lookups --------------------------------------------------------------

    def person_id(self, nconst: str) -> int | None:
        """nconst -> person_id via binary search over the sorted id array.

        A 14M-entry Python dict would cost >1 GB of heap per worker; a
        searchsorted over a memmap costs ~24 comparisons and zero heap.
        """
        key = nconst.encode("ascii", errors="ignore")
        if len(key) > self._id_dtype.itemsize:
            return None
        i = int(np.searchsorted(self.nconst, np.array(key, dtype=self._id_dtype)))
        if i >= len(self.nconst) or self.nconst[i] != key:
            return None
        return i

    def title_of(self, title_id: int) -> Title:
        y = int(self.start_year[title_id])
        return Title(
            tconst=self.tconst[title_id].decode("ascii"),
            primary_title=self.titles.get(title_id),
            title_type=self.types.get(title_id),
            start_year=None if y == -1 else y,
        )

    def person_name(self, person_id: int) -> str:
        return self.names.get(person_id)

    def credits(self, person_id: int) -> np.ndarray:
        a = int(self.postings_off[person_id])
        b = int(self.postings_off[person_id + 1])
        return self.postings[a:b]

    # -- queries --------------------------------------------------------------

    def solo_creator_page(self, offset: int, limit: int):
        """Endpoint 1. The qualifying set is precomputed at build time, so a
        page is an O(limit) slice and `total` is an array length -- no scan."""
        total = int(self.ep1_title_ids.size)
        lo = min(offset, total)
        hi = min(offset + limit, total)
        tids = self.ep1_title_ids[lo:hi]
        pids = self.ep1_person_ids[lo:hi]
        return total, list(zip(tids.tolist(), pids.tolist()))

    def co_starring(self, p1: int, p2: int) -> np.ndarray:
        """Endpoint 2. Intersect two sorted int32 postings lists.

        Both lists are sorted by construction. For the common case (a few
        hundred credits each) np.intersect1d's sort-merge is dominated by
        memory latency on the two slices, which is why the p95 target is
        reachable without any caching layer.
        """
        a = self.credits(p1)
        b = self.credits(p2)
        if a.size == 0 or b.size == 0:
            return np.empty(0, dtype=np.int32)
        # Cheap disjoint-range rejection before doing any real work.
        if a[0] > b[-1] or b[0] > a[-1]:
            return np.empty(0, dtype=np.int32)
        if a.size > b.size:
            a, b = b, a
        # Small vs. huge: binary-search the small side into the big one.
        if b.size > 64 * max(a.size, 1):
            idx = np.searchsorted(b, a)
            idx[idx >= b.size] = b.size - 1
            return a[b[idx] == a]
        return np.intersect1d(a, b, assume_unique=True)
