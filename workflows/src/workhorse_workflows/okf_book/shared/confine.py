"""What an aggregation turn changed, kept to its own pages, with the rest put back.

A turn runs in the repo and could touch anything. Code reads the tree before and after the turn
and keeps a change to a page the job owns, or to a page new since HEAD, under
`docs/features/<service>/`. On any other page of that book it keeps only added lines, such as a
link to a new page, and puts back an edit or a deletion. Every path outside the book is restored.
The entries page is code's alone, so a turn's change to it is restored as well.
"""
from __future__ import annotations

import difflib
import hashlib
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.entries import ENTRIES_NAME, FEATURES_DIR
from workhorse_workflows.okf_book.shared.jobs import Job

_GIT_TIMEOUT = 60


class Snapshot(BaseModel):
    """Each path git reports as changed or untracked, mapped to the sha256 of its content, empty when it is gone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    digests: dict[str, str]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=_GIT_TIMEOUT
    ).stdout


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def snapshot(root: Path) -> Snapshot:
    listed = _git(root, "status", "--porcelain", "-uall", "--no-renames", "-z").split("\0")
    paths = [entry[3:] for entry in listed if len(entry) > 3]
    return Snapshot(digests={path: _digest(root / path) for path in paths})


def changed_since(root: Path, before: Snapshot) -> tuple[str, ...]:
    """Every path whose content differs from what `before` recorded, sorted."""
    after = snapshot(root)
    paths = set(before.digests) | set(after.digests)
    return tuple(sorted(p for p in paths if before.digests.get(p) != after.digests.get(p)))


def _tracked(root: Path, path: str) -> bool:
    return bool(_git(root, "ls-tree", "--name-only", "HEAD", "--", path).strip())


def new_since_head(root: Path, paths: Iterable[str]) -> tuple[str, ...]:
    """The paths HEAD does not track."""
    return tuple(path for path in paths if not _tracked(root, path))


def restore(root: Path, paths: Iterable[str], before: Snapshot) -> tuple[str, ...]:
    """Put each path back as HEAD has it. A path that was already dirty before the turn is left, and returned."""
    left: list[str] = []
    for path in paths:
        if path in before.digests:
            left.append(path)
        elif _tracked(root, path):
            _ = _git(root, "checkout", "HEAD", "--", path)
        else:
            (root / path).unlink(missing_ok=True)
    return tuple(left)


def writable_in_book(service: str, path: str) -> bool:
    """True for a path in the service's book other than its entries page, which no turn writes."""
    folder = (FEATURES_DIR / service).as_posix()
    return path.startswith(f"{folder}/") and path != f"{folder}/{ENTRIES_NAME}"


def draftable(root: Path, job: Job, path: str) -> bool:
    """True for a job's own page, or a markdown page HEAD does not track in the service's book.

    A writer that reads no file rewrites only what it was shown or is creating.
    """
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix != ".md":
        return False
    rel = pure.as_posix()
    if not writable_in_book(job.service, rel):
        return False
    return rel in job.owned_pages or not _tracked(root, rel)


def _is_under(root: Path, path: str, folder: Path) -> bool:
    return (root / path).resolve().is_relative_to(folder.resolve())


def _head_text(root: Path, path: str) -> str | None:
    if not _tracked(root, path):
        return None
    return _git(root, "show", f"HEAD:{path}")


def _adds_only(before: str, after: Path) -> bool:
    if not after.is_file():
        return False
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.read_text(encoding="utf-8").splitlines(), autojunk=False)
    return all(tag in ("equal", "insert") for tag, *_ in matcher.get_opcodes())


def _turn_may_keep(root: Path, job: Job, path: str, before: Snapshot) -> bool:
    if not writable_in_book(job.service, path):
        return False
    head = _head_text(root, path)
    if path in before.digests or head is None or path in job.owned_pages:
        return True
    return _adds_only(head, root / path)


@dataclass(frozen=True, slots=True)
class Confinement:
    """The changed paths a turn keeps, and the changed paths it may not change, which were restored."""

    kept: tuple[str, ...]
    put_back: tuple[str, ...]


def confine(root: Path, job: Job, before: Snapshot, run_dir: Path) -> Confinement:
    """Keep the changed paths the turn may keep, and restore the rest.

    The run's own directory is never restored, when it sits inside the repo.
    """
    changed = tuple(path for path in changed_since(root, before) if not _is_under(root, path, run_dir))
    kept = tuple(path for path in changed if _turn_may_keep(root, job, path, before))
    put_back = tuple(path for path in changed if path not in kept)
    _ = restore(root, put_back, before)
    return Confinement(kept=kept, put_back=put_back)


def book_changes(root: Path, service: str, before: Snapshot) -> tuple[str, ...]:
    """The paths inside the service's book, its entries page left out, whose content changed since `before`."""
    return tuple(path for path in changed_since(root, before) if writable_in_book(service, path))


def revert(root: Path, before: Snapshot, run_dir: Path) -> tuple[str, ...]:
    """Put back every path changed since `before`, the run's own directory aside, and return them."""
    changed = tuple(path for path in changed_since(root, before) if not _is_under(root, path, run_dir))
    _ = restore(root, changed, before)
    return changed


def judged_pages(root: Path, job: Job, before: Snapshot) -> tuple[str, ...]:
    """The job's own pages and the pages it created that changed since `before`, its own first, or its pages when none changed.

    A page the job only added lines to is another job's work, and is not judged as this one's.
    """
    changed = sorted(
        (
            p for p in book_changes(root, job.service, before)
            if p.endswith(".md") and (root / p).is_file() and (p in job.owned_pages or not _tracked(root, p))
        ),
        key=lambda page: (page not in job.owned_pages, page),
    )
    if changed:
        return tuple(changed)
    return (job.page,) if job.page else job.kind_pages
