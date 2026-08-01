"""What was already dirty when a story started, and what still is.

The coder's contract is that a story ends in a commit, so everything between `HEAD` and the
worktree is *this* story's work. That contract has a failure mode: a story that dies before
its commit — a docs failure, a QA give-up, a crash — leaves its production code on disk, and
every story selected after it then diffs against a tree carrying someone else's package.

Two consumers read the same diff and both were wrong in the same way. The docs grounding gate
demanded direct OKF grounding for the abandoned story's symbols, and the QA obligation packet
turned them into scenarios the current story has no business writing. So the reading lives
here rather than in either of them: `snapshot_worktree_state` records the dirty paths with
their bytes before the first dev turn, and `untouched_since` answers which of them the story
has not since touched — the only ones it is safe to subtract.

The subtraction is deliberately one-directional. A path the story *did* edit hashes
differently and stays its responsibility, so the filter can only ever shrink by mistake,
never grow: no story is excused from grounding or testing code it actually wrote.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from git.exc import GitError
from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import WorktreeSnapshot
from workhorse_workflows.kit import open_repo


def digest(root: Path, rel: str) -> str:
    """The sha256 of one worktree file, or `""` when it cannot be read.

    An unreadable path — deleted since the snapshot, or a directory — deliberately digests
    to a value that matches no recorded entry, so it stays in the story's obligation. This
    never subtracts something it cannot positively account for.
    """
    try:
        return hashlib.sha256((root / rel).read_bytes()).hexdigest()
    except OSError:
        return ""


def untouched_since(root: Path, snapshot: tuple[str, ...]) -> set[str]:
    """Which snapshotted paths still hold exactly the bytes they held at story start.

    A path the story went on to edit digests differently and is *not* returned, so it stays
    the story's responsibility — the fail-safe direction described in the module docstring.
    """
    untouched: set[str] = set()
    for entry in snapshot:
        rel, separator, recorded = str(entry).partition("\0")
        if not separator or not rel or not recorded:
            continue
        if digest(root, rel) == recorded:
            untouched.add(rel)
    return untouched


@blueprint.node
def snapshot_worktree_state(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = ""
) -> WorktreeSnapshot:
    """Record what was already dirty before this story's first dev turn.

    Modified *and* untracked, because the case that motivated this is untracked: a story
    that died in its docs phase left a whole new package on disk, and the next story's
    grounding gate demanded seven Go symbols out of it that the next story had never heard
    of and its book had no reason to mention.

    Failing to read the repo returns an empty snapshot rather than raising. An empty
    snapshot subtracts nothing, which is the behaviour both consumers had before this node
    existed — the conservative answer, and the right one for checks meant to fail closed.
    """
    root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    try:
        repo = open_repo(root)
        dirty = [item.a_path for item in repo.index.diff(None) if item.a_path]
        dirty.extend(repo.untracked_files)
    except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.info("could not read the worktree state at %s (%s) — snapshot is empty", root, exc)
        return WorktreeSnapshot(entries=[], notes=f"worktree state unavailable: {exc}")

    entries = [f"{rel}\0{sha}" for rel in sorted(set(dirty)) if (sha := digest(root, rel))]
    logger.info("snapshotted %d pre-existing dirty path(s) at %s", len(entries), root)
    return WorktreeSnapshot(
        entries=entries, notes=f"{len(entries)} path(s) were already dirty when the story started"
    )


__all__ = ["digest", "snapshot_worktree_state", "untouched_since"]
