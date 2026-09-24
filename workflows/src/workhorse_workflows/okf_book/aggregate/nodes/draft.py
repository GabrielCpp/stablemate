"""A page writer's reply, each page's whole text, written into the book where the job may write it."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ostler.api import Ostler
from workhorse_workflows.okf_book.shared.confine import draftable
from workhorse_workflows.okf_book.shared.jobs import Job


class DraftedPage(BaseModel):
    """One page's repo-relative path and its whole text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    text: str


class Drafted(BaseModel):
    """A writer's account of what it changed, and each page it wrote, whole."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    pages: tuple[DraftedPage, ...]


@dataclass(frozen=True, slots=True)
class Applied:
    """The drafted pages written into the book, and the paths the job may not write."""

    written: tuple[str, ...]
    dropped: tuple[str, ...]


def existing_pages(root: Path, pages: Iterable[str]) -> list[str]:
    """The pages that are files in the tree, sorted."""
    return sorted(page for page in pages if (root / page).is_file())


def apply_draft(root: Path, job: Job, pages: tuple[DraftedPage, ...]) -> Applied:
    """Write each drafted page the job may write, then canonicalize their shape. Writing the same draft twice changes nothing."""
    written: list[str] = []
    dropped: list[str] = []
    for page in pages:
        if not draftable(root, job, page.path):
            dropped.append(page.path)
            continue
        target = root / page.path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(page.text if page.text.endswith("\n") else f"{page.text}\n", encoding="utf-8")
        written.append(page.path)
    if written:
        _ = Ostler(root, use_index=False).fmt(*written)
    return Applied(written=tuple(written), dropped=tuple(dropped))
