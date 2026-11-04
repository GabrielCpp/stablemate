"""What the review reads, what the agent reports, and what accounting finds."""
from __future__ import annotations

from pydantic import BaseModel
from workhorse.pyflow import dry_run


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


@dry_run(
    clusters=[{"name": "dry-run", "cause": "dry run", "ids": ["dry-run-1", "dry-run-2", "dry-run-3"]}],
    singletons=[],
    summary="dry run",
)
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


@dry_run(path="trends.md", changed=True)
class TrendsWritten(BaseModel):
    """Where `trends.md` landed and whether this write changed its text."""

    path: str
    changed: bool


@dry_run(name="dry-run", cause="dry run", ids=["dry-run-1", "dry-run-2", "dry-run-3"], lines=[])
class Candidate(BaseModel):
    """One cluster whose unbound records may be enough for a decision."""

    name: str
    cause: str
    ids: list[str]
    lines: list[str]


@dry_run(clusters=[{"name": "dry-run", "cause": "dry run", "ids": ["dry-run-1", "dry-run-2", "dry-run-3"], "lines": []}])
class Candidates(BaseModel):
    """The clusters of a report that reach the decision threshold."""

    clusters: list[Candidate] = []


@dry_run(slug="dry-run", title="Dry run", context="dry run", decision="dry run", consequences="dry run")
class DecisionDraft(BaseModel):
    """The prose of one proposed decision."""

    slug: str
    title: str
    context: str
    decision: str
    consequences: str


@dry_run(ok=True, id="dry-run")
class Filed(BaseModel):
    """What proposing one decision came to: its id, or the refusal."""

    ok: bool
    id: str = ""
    message: str = ""


class Proposed(BaseModel):
    """The ids of the decisions a run proposed."""

    decisions: list[str] = []
