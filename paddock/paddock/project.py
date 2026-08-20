"""Pin the project a run drives, so a round measures one state of the code.

A task drives stablemate's own CLIs out of a checkout — `uv run --project <checkout>
workhorse-coder run …`. Left as the operator's working tree, that checkout is being
edited while the round runs: a forty-minute trial can start on one workflow source and
finish on another, and nothing in the result says which one it measured. It also makes
the "did the round commit into the harness instead of its sandbox" check unanswerable,
because an operator commit and a leaked agent commit land in the same tree and look
identical.

So paddock gives the run a tree of its own: a detached `git worktree` at the checkout's
HEAD, created before the first step and removed after sealing. Three things follow, and
they are the whole reason:

* the pinned sha goes into `steps.json`, so the ledger says which code produced the
  numbers;
* uncommitted edits are **excluded** — a round measures committed state, and a dirty
  checkout is warned about rather than silently included;
* any commit in the trial tree is a leak by construction, since nobody else has a reason
  to write there.

The cost is one `uv sync` per run into the worktree's own `.venv` (wheels come from uv's
cache, so it is seconds, not a build) and the disk that venv takes until release.

What this does *not* pin is the data directory: the answer key, the fixture app and the
result pointers are read and written in the operator's tracked tree on purpose — a score
whose ruler travelled inside the thing being measured would be worse than an unpinned one.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Project:
    """The tree a run's steps drive, and where it came from."""

    #: What a step should pass to `uv run --project` and stand in.
    path: Path
    #: The checkout `path` was pinned from — `path` itself when nothing was pinned.
    source: Path
    #: The commit the round ran at; empty when the source is not a git repository.
    head: str
    #: False when the run drives the operator's tree directly (`--no-pin-project`, or a
    #: source git cannot make a worktree of).
    pinned: bool
    #: Whether the source had uncommitted changes at pin time. Recorded because those
    #: changes are exactly what a pinned run did *not* see.
    dirty: bool

    def as_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "source": str(self.source),
            "head": self.head,
            "pinned": self.pinned,
            "source_dirty": self.dirty,
        }


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def pin(source: Path | None, *, work: Path, enabled: bool = True) -> Project | None:
    """A detached worktree of *source* at its HEAD, under *work*.

    Degrades rather than fails: a source that is not a git repository, or a `git worktree
    add` that will not run, leaves the run driving the operator's tree with `pinned:
    False` in the ledger. A benchmark that refuses to start because the harness could not
    make a worktree helps nobody; a benchmark that silently claims a provenance it does
    not have is the failure worth avoiding, and the flag in the ledger is what avoids it.
    """
    if source is None:
        return None
    source = source.resolve()
    head = _git("rev-parse", "HEAD", cwd=source)
    if head.returncode != 0:
        logger.warning("project %s is not a git checkout — running unpinned", source)
        return Project(path=source, source=source, head="", pinned=False, dirty=False)
    sha = head.stdout.strip()
    dirty = bool(_git("status", "--porcelain", cwd=source).stdout.strip())
    if not enabled:
        return Project(path=source, source=source, head=sha, pinned=False, dirty=dirty)

    dest = work / "project"
    # A worktree whose directory was deleted out from under git stays registered, and
    # `add` onto its path fails with "already registered" until the record is dropped.
    _git("worktree", "prune", cwd=source)
    if dest.exists():
        release(Project(path=dest, source=source, head=sha, pinned=True, dirty=dirty))
    added = _git("worktree", "add", "--detach", str(dest), sha, cwd=source)
    if added.returncode != 0:
        logger.warning(
            "could not pin %s to a worktree (%s) — running unpinned",
            source, added.stderr.strip(),
        )
        return Project(path=source, source=source, head=sha, pinned=False, dirty=dirty)
    if dirty:
        logger.warning(
            "%s has uncommitted changes; this run is pinned to %s and will not see them",
            source, sha[:12],
        )
    logger.info("project pinned to %s at %s", dest, sha[:12])
    return Project(path=dest, source=source, head=sha, pinned=True, dirty=dirty)


def release(project: Project | None) -> None:
    """Remove a pinned worktree, and never let that failure end a run.

    The result is already sealed by the time this runs, so a worktree that will not go
    away is a disk-space problem to report, not a round to fail.
    """
    if project is None or not project.pinned:
        return
    removed = _git("worktree", "remove", "--force", str(project.path), cwd=project.source)
    if removed.returncode == 0:
        return
    logger.warning("git worktree remove failed (%s) — deleting the tree", removed.stderr.strip())
    shutil.rmtree(project.path, ignore_errors=True)
    _git("worktree", "prune", cwd=project.source)
