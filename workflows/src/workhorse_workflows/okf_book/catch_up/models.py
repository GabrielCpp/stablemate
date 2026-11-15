"""What the catch-up flow reads from a book's stale report, what it records of each book, and what its owner turn says."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CURRENT = "current"
FIRST_BOOK = "first-book"
STALE = "stale"
UNJUDGED = "unjudged"


class ModuleReport(BaseModel):
    """What the book's stale said of one module: the commit it was verified at, the elements whose source changed with the files, and the changed files no element names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: str
    verdict: Literal["current", "first-book", "stale", "unjudged"]
    verified: str = ""
    elements: dict[str, list[str]] = Field(default_factory=dict)
    new_files: list[str] = Field(default_factory=list)
    gone: list[str] = Field(default_factory=list)
    output: str = ""
    exit_code: int = 0
    error: str = ""

    @property
    def files(self) -> list[str]:
        """Every file of the app the diff is read over."""
        found = {pointer.split("::", 1)[0] for pointers in self.elements.values() for pointer in pointers}
        return sorted(found | set(self.new_files))


class BookReport(BaseModel):
    """What the stale reports of every module of one service say."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    modules: list[ModuleReport] = Field(default_factory=list)

    @property
    def verdict(self) -> str:
        verdicts = {module.verdict for module in self.modules}
        for kind in (UNJUDGED, FIRST_BOOK, STALE):
            if kind in verdicts:
                return kind
        return CURRENT

    @property
    def elements(self) -> list[str]:
        return sorted({name for module in self.modules for name in module.elements})


class BookOutcome(BaseModel):
    """How the run left one book."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    verdict: Literal["current", "caught-up", "first-book"]
    laps: int = 0
    elements: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    ignored: list[str] = Field(default_factory=list)


class Filed(BaseModel):
    """What the fill found, by service, and for each book whose stale report could not be read what the command printed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stale: list[str] = Field(default_factory=list)
    settled: list[str] = Field(default_factory=list)
    unread: dict[str, str] = Field(default_factory=dict)


class CatchUpReply(BaseModel):
    """What the owner's turn says it did, or what stopped it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    done: str = Field(default="", description="What the book now says that it did not, in a sentence or two.")
    blocked: str = Field(default="", description="Only when you could not finish: what an operator must decide or fix.")
    added: list[str] = Field(default_factory=list, description="The class name of each endpoint or interaction you added to the book, as the book spells it.")
    ignored: list[str] = Field(default_factory=list, description="Each pattern you added to the service's `App(ignore=...)`, as written there.")


class CatchUpOutcome(BaseModel):
    """The books the run judged and how it left each."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    books: list[BookOutcome] = Field(default_factory=list)
    summary: str = ""
