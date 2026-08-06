from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Person(BaseModel):
    nconst: str
    primaryName: str


class TitleOut(BaseModel):
    tconst: str
    primaryTitle: str
    titleType: str
    startYear: int | None = None


class SoloCreatorItem(TitleOut):
    person: Person


class Page(BaseModel, Generic[T]):
    total: int = Field(..., description="total number of matching rows, not just this page")
    page: int
    pageSize: int
    items: list[T]


class Health(BaseModel):
    status: str
    indexBuiltAt: str | None = None
    stats: dict | None = None
