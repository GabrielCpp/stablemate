"""What the review reads, what the agent reports, and what accounting finds."""
from __future__ import annotations

from pydantic import BaseModel


class CompleteRead(BaseModel):
    """Every parseable record of every status in every repository, and the files that did not parse."""

    ids: list[str] = []
    listing: list[str] = []
    shelf: str = ""
    unreadable: list[str] = []


class Cluster(BaseModel):
    """Two or more records that share one cause."""

    name: str
    cause: str
    ids: list[str]


class Singleton(BaseModel):
    """One record whose cause no other record shares."""

    id: str
    cause: str


class TrendReport(BaseModel):
    """The clusters, the singletons and a paragraph for the maintainer."""

    clusters: list[Cluster]
    singletons: list[Singleton]
    summary: str


class Accounting(BaseModel):
    """Whether every id of the read appears in the report exactly once."""

    missing: list[str] = []
    duplicated: list[str] = []
    unknown: list[str] = []

    @property
    def ok(self) -> bool:
        return not (self.missing or self.duplicated or self.unknown)


class TrendsWritten(BaseModel):
    """Where `trends.md` landed and whether this write committed anything."""

    path: str
    committed: bool
