"""Pin the project a run drives, so a round measures one state of the code.

A task drives stablemate's own CLIs out of a checkout — `uv run --project <checkout>
workhorse-coder run …`. Left as the operator's working tree, that checkout is being
edited while the round runs: a forty-minute trial can start on one workflow source and
finish on another, and nothing in the result says which one it measured. It also makes
the "did the round commit into the harness instead of its sandbox" check unanswerable,
because an operator commit and a leaked agent commit land in the same tree and look
identical.

So paddock gives the run a repository of its own: a local clone of the checkout, with
**every remote removed**, checked out detached at the checkout's HEAD, created before the
first step and deleted after sealing. Three things follow, and they are the whole reason:

* the pinned sha goes into `steps.json`, so the ledger says which code produced the
  numbers;
* uncommitted edits are **excluded** — a round measures committed state, and a dirty
  checkout is warned about rather than silently included;
* any commit in the trial tree is a leak by construction, since nobody else has a reason
  to write there.

A clone rather than a `git worktree`, and remoteless rather than merely detached, because
a worktree of the live checkout shares its object store *and* its `origin`. One round
proved what that costs: an agent working inside the pinned tree read the toolchain repo's
own AGENTS.md — "push it now, right after the commit" — obeyed it to the letter, hit a
rejection, and followed the reconcile procedure written directly beneath it. Its commits
reached the public repo. The agent was not rogue; it was obedient in the wrong context,
and no instruction file can be trusted to say "unless you are a benchmark subject". Zero
remotes is what makes a push fail loudly instead of succeeding, and the failure lands in
the run record where a reader will find it.

The cost is one `uv sync` per run into the clone's own `.venv` (wheels come from uv's
cache, so it is seconds, not a build) and the disk that venv takes until release. The
clone itself is local, so git hardlinks the objects and it is neither.

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
    """A remoteless clone of *source*, detached at its HEAD, under *work*.

    Degrades rather than fails: a source that is not a git repository, or a clone that
    will not run, leaves the run driving the operator's tree with `pinned: False` in the
    ledger. A benchmark that refuses to start because the harness could not make a clone
    helps nobody; a benchmark that silently claims a provenance it does not have is the
    failure worth avoiding, and the flag in the ledger is what avoids it.

    The one thing it will not degrade past is the remote. A clone that kept `origin`
    would be a pin in name only, so a failure to strip it discards the tree and runs
    unpinned rather than handing a round a route to the network.
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
    # Re-running a label reuses its work directory, and a clone will not write into a
    # path that already exists.
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    unpinned = Project(path=source, source=source, head=sha, pinned=False, dirty=dirty)
    # `--no-checkout`, because the branch a clone would land on is not the state being
    # pinned: the detached checkout below is, and doing it in one step would write the
    # tree twice.
    cloned = _git("clone", "--quiet", "--no-checkout", str(source), str(dest), cwd=work.parent)
    if cloned.returncode != 0:
        logger.warning(
            "could not clone %s (%s) — running unpinned", source, cloned.stderr.strip()
        )
        return unpinned
    for remote in _git("remote", cwd=dest).stdout.split():
        if _git("remote", "remove", remote, cwd=dest).returncode != 0:
            logger.warning(
                "could not strip remote %r from the pin of %s — running unpinned, and "
                "deleting the clone rather than leaving a round a route to the network",
                remote, source,
            )
            shutil.rmtree(dest, ignore_errors=True)
            return unpinned
    checked_out = _git("checkout", "--detach", sha, cwd=dest)
    if checked_out.returncode != 0:
        logger.warning(
            "could not check %s out at %s (%s) — running unpinned",
            source, sha[:12], checked_out.stderr.strip(),
        )
        shutil.rmtree(dest, ignore_errors=True)
        return unpinned
    if dirty:
        logger.warning(
            "%s has uncommitted changes; this run is pinned to %s and will not see them",
            source, sha[:12],
        )
    logger.info("project pinned to %s at %s", dest, sha[:12])
    return Project(path=dest, source=source, head=sha, pinned=True, dirty=dirty)


def release(project: Project | None) -> None:
    """Delete a pinned clone, and never let that failure end a run.

    The result is already sealed by the time this runs, so a tree that will not go away is
    a disk-space problem to report, not a round to fail. A clone is nothing but its own
    directory — no registration in the source repository to unwind, which is the other
    half of why it replaced the worktree.
    """
    if project is None or not project.pinned:
        return
    shutil.rmtree(project.path, ignore_errors=True)
    if project.path.exists():
        logger.warning("could not delete the pinned clone at %s", project.path)
