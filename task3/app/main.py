"""HTTP layer. Thin on purpose: all the work happens in app/index.py."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from app import config
from app.index import ImdbIndex
from app.schemas import Health, Page, Person, SoloCreatorItem, TitleOut

_state: dict[str, ImdbIndex | None] = {"index": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loading is just mmap()s and a meta.json read, so startup is O(number of
    # files), not O(dataset). The pages fault in lazily on first touch.
    path = Path(os.getenv("IMDB_INDEX_DIR", str(config.INDEX_DIR)))
    _state["index"] = ImdbIndex(path)
    yield
    _state["index"] = None


app = FastAPI(
    title="IMDb REST service",
    version="1.0.0",
    summary="Two read-only endpoints over the full public IMDb dataset.",
    lifespan=lifespan,
)


def get_index() -> ImdbIndex:
    idx = _state["index"]
    if idx is None:
        raise HTTPException(status_code=503, detail="index not loaded")
    return idx


@app.get("/health", response_model=Health)
def health() -> Health:
    idx = _state["index"]
    if idx is None:
        return Health(status="loading")
    return Health(
        status="ok",
        indexBuiltAt=idx.meta.get("built_at"),
        stats=idx.meta.get("stats"),
    )


@app.get("/meta")
def meta(idx: ImdbIndex = Depends(get_index)) -> dict:
    """Full build metadata, including the alive-criterion actually used."""
    return idx.meta


@app.get(
    "/v1/titles/solo-creator",
    response_model=Page[SoloCreatorItem],
    summary="Titles whose director and writer are the same single, living person",
)
def solo_creator(
    page: int = Query(1, ge=1),
    pageSize: int = Query(config.DEFAULT_PAGE_SIZE, ge=1, le=config.MAX_PAGE_SIZE),
    idx: ImdbIndex = Depends(get_index),
) -> Page[SoloCreatorItem]:
    offset = (page - 1) * pageSize
    total, rows = idx.solo_creator_page(offset, pageSize)
    items = []
    for tid, pid in rows:
        t = idx.title_of(tid)
        items.append(
            SoloCreatorItem(
                tconst=t.tconst,
                primaryTitle=t.primary_title,
                titleType=t.title_type,
                startYear=t.start_year,
                person=Person(
                    nconst=idx.nconst[pid].decode("ascii"),
                    primaryName=idx.person_name(pid),
                ),
            )
        )
    return Page[SoloCreatorItem](total=total, page=page, pageSize=pageSize, items=items)


@app.get(
    "/v1/titles/co-starring",
    response_model=Page[TitleOut],
    summary="Titles in which two given actors both appeared",
)
def co_starring(
    actor1: str = Query(..., pattern=r"^nm\d{1,12}$", examples=["nm0000138"]),
    actor2: str = Query(..., pattern=r"^nm\d{1,12}$", examples=["nm0000093"]),
    page: int = Query(1, ge=1),
    pageSize: int = Query(config.DEFAULT_PAGE_SIZE, ge=1, le=config.MAX_PAGE_SIZE),
    idx: ImdbIndex = Depends(get_index),
) -> Page[TitleOut]:
    p1 = idx.person_id(actor1)
    if p1 is None:
        raise HTTPException(404, detail=f"unknown nconst: {actor1}")
    p2 = idx.person_id(actor2)
    if p2 is None:
        raise HTTPException(404, detail=f"unknown nconst: {actor2}")
    if p1 == p2:
        raise HTTPException(400, detail="actor1 and actor2 must differ")

    hits = idx.co_starring(p1, p2)
    total = int(hits.size)
    offset = (page - 1) * pageSize
    window = hits[offset : offset + pageSize]
    items = []
    for tid in window.tolist():
        t = idx.title_of(tid)
        items.append(
            TitleOut(
                tconst=t.tconst,
                primaryTitle=t.primary_title,
                titleType=t.title_type,
                startYear=t.start_year,
            )
        )
    return Page[TitleOut](total=total, page=page, pageSize=pageSize, items=items)
