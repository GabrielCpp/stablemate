"""The book's stale report, read into the elements and files it names."""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from workhorse_workflows.okf_book.catch_up.models import CURRENT, ELEMENTS_LISTED, FIRST_BOOK, STALE, UNJUDGED, ModuleCheck, ModuleReport, NoteKind, NoteKindMove
from workhorse_workflows.okf_book.shared.book_gates import note_lines

STALE_ELEMENTS = "## Stale elements"
UNNAMED_FILES = "## Changed files no element names"
UNNAMED_FUNCTIONS = "## Changed functions no element names"
BESIDE = "## Changed beside the named symbols, functions not told apart"
GONE = "## Pointers to files that no longer exist"
ELEMENT_LINE = re.compile(r"^- (\w+): (\S+) \(\d+ commits?:")
FILE_LINE = re.compile(r"^- (\S+) \(\d+ commits?:.*?\)(?: named by (.+))?$")
VERIFIED_LINE = re.compile(r"^verified at (\S+), app at (\S+)$")
GONE_LINE = re.compile(r"^- (\w+): (\S+)$")
CHECK_PREFIX = "CHECK"
NOTE_PREFIX = "NOTE"
CHECK_TOTAL = re.compile(r"^check: (\d+) findings?(?:, (\d+) notes?)?$")
NOT_VERIFIED = "not verified"
NO_APP_LINE = re.compile(r"^\S+ declares no app$")
NOTHING_STALE = 0
SOME_STALE = 1
COULD_NOT_READ = 2
KIND_CHARS = 60


@dataclass
class _Read:
    verified: str = ""
    elements: dict[str, list[str]] = field(default_factory=dict)
    new_files: list[str] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)

    def take(self, section: str, line: str) -> None:
        """File one line of a section under what it names."""
        if section == STALE_ELEMENTS and (element := ELEMENT_LINE.match(line)):
            self.elements.setdefault(element.group(1), []).append(element.group(2))
        elif section in (UNNAMED_FILES, UNNAMED_FUNCTIONS) and (named := FILE_LINE.match(line)):
            path = named.group(1).split("::", 1)[0]
            if path not in self.new_files:
                self.new_files.append(path)
        elif section == BESIDE and (beside := FILE_LINE.match(line)) and beside.group(2):
            for name in beside.group(2).split(", "):
                self.elements.setdefault(name, []).append(beside.group(1))
        elif section == GONE and (pointer := GONE_LINE.match(line)):
            self.elements.setdefault(pointer.group(1), [])
            self.gone.append(f"{pointer.group(1)}: {pointer.group(2)}")


def read_stale(module: str, exit_code: int, stdout: str, stderr: str = "") -> ModuleReport:
    """The module's verdict from the stale command's exit code, and for a stale one the elements, files and pointers it printed."""
    if exit_code == NOTHING_STALE:
        return ModuleReport(module=module, verdict=CURRENT)
    if exit_code == COULD_NOT_READ and (NOT_VERIFIED in stdout or NO_APP_LINE.match(stdout.strip())):
        return ModuleReport(module=module, verdict=FIRST_BOOK)
    if exit_code != SOME_STALE:
        return ModuleReport(module=module, verdict=UNJUDGED, output=stdout.strip(), exit_code=exit_code, error=stderr.strip())
    read = _Read()
    section = ""
    for line in stdout.splitlines():
        if found := VERIFIED_LINE.match(line):
            read.verified = found.group(1)
        elif line.startswith("## "):
            section = line
        else:
            read.take(section, line)
    return ModuleReport(module=module, verdict=STALE, verified=read.verified, elements=read.elements, new_files=read.new_files, gone=read.gone)


def read_check(module: str, exit_code: int, output: str, noted: Sequence[str] | None = None) -> ModuleCheck:
    """The module's findings from the check's output: the lines it printed as findings, the notes it printed, and the counts of its last line. A red check that printed neither gives its whole output as the findings. `noted` is every note the check printed when *output* is only its tail."""
    lines = [line[len(CHECK_PREFIX):].strip() for line in output.splitlines() if line.startswith(f"{CHECK_PREFIX} ")]
    printed = list(noted) if noted is not None else list(note_lines(output))
    total = next((CHECK_TOTAL.match(line) for line in reversed(output.splitlines()) if CHECK_TOTAL.match(line)), None)
    if total is not None:
        return ModuleCheck(module=module, exit_code=exit_code, findings=int(total.group(1)), notes=max(int(total.group(2) or 0), len(printed)), lines=lines, noted=printed)
    if exit_code != 0 and not lines:
        lines = [line for line in output.splitlines() if line.strip()]
    return ModuleCheck(module=module, exit_code=exit_code, findings=len(lines), notes=len(printed), lines=lines, noted=printed)


def split_note(note: str) -> tuple[str, str]:
    """The element a note names and its kind. The kind is the text after the element's name and its colon, cut at the next colon or at 60 characters, so notes that differ only in the element and in what follows the colon are one kind."""
    element, found, problem = note.partition(": ")
    if not found:
        return "", note[:KIND_CHARS].strip()
    return element.strip(), problem.split(":", 1)[0][:KIND_CHARS].strip()


def _head(line: str) -> str:
    return line.partition(": ")[0].strip()


def declined_heads(declined: Iterable[str]) -> set[str]:
    """What each declined line names before its colon: an element or a kind of note."""
    return {head for line in declined if (head := _head(line))}


def is_declined(note: str, heads: set[str]) -> bool:
    """Whether a declined line names the note's kind or its element, with or without the element's leading word such as `screen`."""
    element, kind = split_note(note)
    return kind in heads or element in heads or (" " in element and element.partition(" ")[2] in heads)


def undeclined(notes: Iterable[str], declined: Iterable[str]) -> list[str]:
    """The notes no declined line covers."""
    heads = declined_heads(declined)
    return [note for note in notes if not is_declined(note, heads)]


def note_kinds(notes: Iterable[str]) -> list[NoteKind]:
    """The notes grouped by kind, the largest kind first, each with its elements in the order the check printed them."""
    found: dict[str, list[str]] = {}
    for note in notes:
        element, kind = split_note(note)
        found.setdefault(kind, []).append(element)
    return [NoteKind(kind=kind, elements=elements) for kind, elements in sorted(found.items(), key=lambda item: (-len(item[1]), item[0]))]


def note_listing(notes: Iterable[str]) -> str:
    """The notes as text for a question or a gate: each kind with its count and its elements, at most 80 of them, and how many more."""
    out: list[str] = []
    for group in note_kinds(notes):
        out.append(f"{group.kind}: {group.count}")
        out.extend(f"- {element}" for element in group.elements[:ELEMENTS_LISTED])
        if group.more:
            out.append(f"- and {group.more} more")
    return "\n".join(out)


def kind_moves(before: Iterable[str], after: Iterable[str], declined: Iterable[str]) -> list[NoteKindMove]:
    """For each kind of note the book was filed with, how many there were, how many are left, and how many of those left are declined."""
    heads = declined_heads(declined)
    left = list(after)
    moves: list[NoteKindMove] = []
    for group in note_kinds(before):
        here = [note for note in left if split_note(note)[1] == group.kind]
        moves.append(NoteKindMove(kind=group.kind, before=group.count, after=len(here), declined=sum(1 for note in here if is_declined(note, heads))))
    return moves


def owed_notes(before: Iterable[str], after: Iterable[str], declined: Iterable[str]) -> list[str]:
    """The notes the check still prints of a kind the book was filed with, that no declined line covers."""
    filed = {split_note(note)[1] for note in before}
    return [note for note in undeclined(after, declined) if split_note(note)[1] in filed]
