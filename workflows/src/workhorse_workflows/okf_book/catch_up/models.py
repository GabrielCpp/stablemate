"""What the catch-up flow reads from a book's stale report, what it records of each book, and what its owner turn says."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from workhorse_workflows.okf_book.shared.book_format import FormatDelta

CURRENT = "current"
FIRST_BOOK = "first-book"
STALE = "stale"
UNJUDGED = "unjudged"
ELEMENTS_LISTED = 80


class Roots(BaseModel):
    """Where the catch-up reads: the book root, the app, and the checkout that holds the book format's history, empty for the one the workflow runs from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    book: Path
    app: Path
    history: str = ""


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


class NoteKind(BaseModel):
    """The notes of one kind the check printed: the kind and the element each one names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    elements: list[str] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.elements)

    @property
    def more(self) -> int:
        return max(0, self.count - ELEMENTS_LISTED)


class ModuleCheck(BaseModel):
    """What the book's check said of one module: its exit code, the findings and notes it counted, and the finding lines it printed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module: str
    exit_code: int = 0
    findings: int = 0
    notes: int = 0
    lines: list[str] = Field(default_factory=list)
    noted: list[str] = Field(default_factory=list)

    @property
    def red(self) -> bool:
        return self.exit_code != 0

    @property
    def unlisted(self) -> int:
        return max(0, self.findings - len(self.lines))


class BookReport(BaseModel):
    """What the stale reports and the checks of every module of one service say, the writer's history when it could be read, and whether the book is filed for the format alone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    modules: list[ModuleReport] = Field(default_factory=list)
    format: FormatDelta | None = None
    checks: list[ModuleCheck] = Field(default_factory=list)

    @property
    def for_format(self) -> bool:
        """Whether the check's findings or notes are work for this book, which is the one place that says so: a check that is red or that printed notes when the book was filed."""
        return any(check.red or check.noted for check in self.checks)

    @property
    def noted(self) -> list[str]:
        return [note for check in self.checks for note in check.noted]

    @property
    def format_behind(self) -> bool:
        return self.format is not None and self.format.behind

    @property
    def check_findings(self) -> int:
        return sum(check.findings for check in self.checks)

    @property
    def check_notes(self) -> int:
        return sum(check.notes for check in self.checks)

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


class NoteKindMove(BaseModel):
    """How far one kind of note went: its count when the book was filed, its count after the last lap, and how many of those left are declined."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    before: int = 0
    after: int = 0
    declined: int = 0

    @property
    def said(self) -> str:
        """The kind with its counts as one line."""
        line = f"{self.kind}: {self.before} to {self.after}"
        return f"{line} ({self.declined} declined)" if self.declined else line


class FormatMove(BaseModel):
    """What an operator reads to accept a book moved onto the format: the check's findings and notes before the owner's first lap and after the last, each kind of note with its counts, the calls and journeys played with the play's exit, and what a whole play is owed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings_before: int = 0
    findings_after: int = 0
    notes_before: int = 0
    notes_after: int = 0
    kinds: list[NoteKindMove] = Field(default_factory=list)
    calls: int = 0
    journeys: int = 0
    exit_code: int | None = None
    owed: str = ""


class BookOutcome(BaseModel):
    """How the run left one book."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    verdict: Literal["current", "caught-up", "first-book"]
    laps: int = 0
    elements: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    ignored: list[str] = Field(default_factory=list)
    app: bool = True
    moved: bool = False
    format: list[str] = Field(default_factory=list)
    move: FormatMove | None = None
    declined: list[str] = Field(default_factory=list)


class Filed(BaseModel):
    """What the fill found, by service, and for each book whose stale report or check could not be read what the command printed."""

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
    format: list[str] = Field(default_factory=list, description="One line for each format change listed above, `<short sha> applied: <what you changed>` or `<short sha> not applicable: <why>`.")
    declined: list[str] = Field(default_factory=list, description="One line for each note you judged not to apply, `<Element>: <reason>`, or `<kind>: <reason>` for a whole kind of note the book is not moving onto.")


class CatchUpOutcome(BaseModel):
    """The books the run judged and how it left each."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    books: list[BookOutcome] = Field(default_factory=list)
    summary: str = ""
