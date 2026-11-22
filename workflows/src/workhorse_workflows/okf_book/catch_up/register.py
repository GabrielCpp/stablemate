"""The register of declined notes: what a book declines of the check's notes, kept in the book beside its package so the next run does not ask again."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from workhorse._vendor.stablemate_core import books

KIND_CHARS = 60
REGISTER_FILE = "DECLINED.md"
WHOLE_KIND = "*"
HEADING = "# Notes the check prints that this book declines, one line each: `- <element>: <kind>: <reason>`, `*` for a whole kind"


def split_note(note: str) -> tuple[str, str]:
    """The element a note names and its kind. The kind is the text after the element's name and its colon, cut at the next colon or at 60 characters, so notes that differ only in the element and in what follows the colon are one kind."""
    element, found, problem = note.partition(": ")
    if not found:
        return "", note[:KIND_CHARS].strip()
    return element.strip(), problem.split(":", 1)[0][:KIND_CHARS].strip()


def _pair(entry: str) -> tuple[str, str]:
    element, _, rest = entry.partition(": ")
    return element.strip(), rest.partition(": ")[0].strip()


def is_declined(note: str, register: Iterable[str]) -> bool:
    """Whether the register holds the note's element and kind, or its kind for every element."""
    element, kind = split_note(note)
    pairs = {_pair(entry) for entry in register}
    return (WHOLE_KIND, kind) in pairs or (element, kind) in pairs


def undeclined(notes: Iterable[str], register: Iterable[str]) -> list[str]:
    """The notes no register entry covers."""
    entries = list(register)
    return [note for note in notes if not is_declined(note, entries)]


def declined_notes(notes: Iterable[str], register: Iterable[str]) -> list[str]:
    """The notes a register entry covers."""
    entries = list(register)
    return [note for note in notes if is_declined(note, entries)]


def entries_for(lines: Iterable[str], notes: Sequence[str]) -> list[str]:
    """The register entries for the lines an owner turn declined with, `<Element>: <reason>` or `<kind>: <reason>`, read against the notes the check prints. A line that names neither a kind nor an element of those notes gives no entry."""
    kinds = {split_note(note)[1] for note in notes}
    found: dict[tuple[str, str], str] = {}
    for line in lines:
        head, colon, said = line.partition(": ")
        head, reason = head.strip(), " ".join(said.split())
        if not colon or not head or not reason:
            continue
        if head in kinds:
            found[(WHOLE_KIND, head)] = f"{WHOLE_KIND}: {head}: {reason}"
            continue
        for note in notes:
            element, kind = split_note(note)
            if head == element or (" " in element and element.partition(" ")[2] == head):
                found[(element, kind)] = f"{element}: {kind}: {reason}"
    return list(found.values())


def register_path(root: Path, service: str, package: str = "services") -> Path:
    return root / books.package_folder(package) / service / REGISTER_FILE


def read_register(root: Path, service: str, package: str = "services") -> list[str]:
    """Every entry of the book's register, in file order, or none when the book has no register."""
    path = register_path(root, service, package)
    if not path.is_file():
        return []
    return [line[2:].strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]


def write_register(root: Path, service: str, entries: Iterable[str], package: str = "services") -> list[str]:
    """Merge *entries* into the book's register, a later entry for the same element and kind replacing an earlier one, write the file and return all entries."""
    merged = {_pair(entry): entry for entry in [*read_register(root, service, package), *entries]}
    path = register_path(root, service, package)
    _ = path.write_text("\n".join([HEADING, "", *(f"- {entry}" for entry in merged.values())]) + "\n", encoding="utf-8")
    return list(merged.values())
