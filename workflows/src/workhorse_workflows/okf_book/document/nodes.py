"""The document turns: which files the next turn reads, and what each file shows it.

A turn reads each of its files whole, the names its direct imports declare but none of their
bodies, and the check vocabulary. Files go in work-set order while they fit the budget, and a
file over the budget goes alone.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ostler.checks import CHECKS, CheckSpec
from ostler.inventory import symbols
from workhorse_workflows.okf_book.shared.attempts import FailureTally, last_problems
from workhorse_workflows.okf_book.shared.budget import (
    PACKAGE_DIR,
    ALONE_CEILING_TOKENS,
    TURN_BUDGET_TOKENS,
    Packed,
    estimated_tokens,
    name_tokens,
    pack_told,
)
from workhorse_workflows.okf_book.shared.entries import read_entries, services
from workhorse_workflows.okf_book.shared.imports import neighbours

DOCUMENT_PROMPT = "document/prompts/document-files.md"
ENTRY_POINTS_BUDGET_TOKENS = 2_000


def check_vocabulary() -> tuple[str, ...]:
    """Every check's signature and what it reads on a cli, as the turn reads it."""
    return tuple(_described(spec) for spec in CHECKS)


def _described(spec: CheckSpec) -> str:
    if spec.on_cli:
        return f"`{spec.signature()}`. On a cli, reads {spec.on_cli}."
    if spec.out_of_band:
        return f"`{spec.signature()}`"
    return f"`{spec.signature()}`. On a cli, reads nothing a command shows."


@dataclass(frozen=True, slots=True)
class FileBrief:
    """One file as a document turn reads it: its body, its imports' declared names, and its last problems."""

    file: str
    body: str
    imports: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def tokens(self) -> int:
        lines = (*self.imports, *self.problems)
        return estimated_tokens(len(self.file) + len(self.body) + sum(len(line) for line in lines))

    def template_arg(self) -> dict[str, object]:
        return {"file": self.file, "body": self.body, "imports": self.imports, "problems": self.problems}


def _declared(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ", ".join(symbols(path, text))


def file_brief(root: Path, file: str, problems: tuple[str, ...] = ()) -> FileBrief:
    path = root / file
    lines = tuple(
        f"{found.relative_to(root).as_posix()}: {_declared(found)}"
        for found in dict.fromkeys(neighbours(root, path.resolve()))
        if found != path.resolve()
    )
    return FileBrief(file, path.read_text(encoding="utf-8", errors="replace"), lines, problems)


def entry_points(root: Path) -> Packed:
    """Each way a user drives the product, as its service's book lists it, kept while they fit their budget."""
    names = (f"{service}: {link.title}" for service in services(root) for link in read_entries(root, service))
    return pack_told(name_tokens(names), ENTRY_POINTS_BUDGET_TOKENS)


def fixed_tokens(root: Path) -> int:
    """What the prompt, the entry points and the check vocabulary cost before any file is read."""
    prompt = (PACKAGE_DIR / DOCUMENT_PROMPT).read_text(encoding="utf-8")
    vocabulary = sum(len(line) for line in check_vocabulary())
    return estimated_tokens(len(prompt) + vocabulary) + entry_points(root).tokens


@dataclass(frozen=True, slots=True)
class Batch:
    """The files one document turn reads, or the one file too large for any turn."""

    briefs: tuple[FileBrief, ...]
    tokens: int
    oversized_file: str = ""

    @property
    def files(self) -> tuple[str, ...]:
        return tuple(brief.file for brief in self.briefs)


def next_batch(root: Path, pending: Sequence[str], attempts: Iterable[FailureTally], budget: int = TURN_BUDGET_TOKENS) -> Batch:
    """The next pending files that fit one turn, in order. A first file past the ceiling comes back alone as too large."""
    kept_attempts = tuple(attempts)
    fixed = fixed_tokens(root)
    room = max(budget - fixed, 0)
    briefs: list[FileBrief] = []
    spent = 0
    for file in pending:
        brief = file_brief(root, file, last_problems(kept_attempts, file))
        if not briefs and brief.tokens > ALONE_CEILING_TOKENS:
            return Batch((brief,), fixed + brief.tokens, oversized_file=file)
        if briefs and spent + brief.tokens > room:
            break
        briefs.append(brief)
        spent += brief.tokens
    return Batch(tuple(briefs), fixed + spent)
