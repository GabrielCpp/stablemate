#!/usr/bin/env python3
"""Check out (or create) the epic branch and reconcile the epic queue.

Args: <epic> [<base_branch>]

An existing feat/<epic> branch is treated as stale, not resumed: once an
epic's PR merges (typically via squash) its branch no longer reflects the
current epic queue, and a leftover branch under that name may even hold an
entirely different epic's abandoned work (e.g. a past branch/epic-name
mismatch). Reusing it risks silently continuing on stale or unrelated
content instead of the current story set, and — since it's a real checkout
of a possibly-diverged tree — can also fail outright against a dirty working
tree, which used to go undetected (see the exit-code check below). So any
existing feat/<epic> is renamed aside to archive/<epic>-<short-sha> (nothing
is deleted — the old ref stays reachable under that name) and a fresh
feat/<epic> is always cut from the current HEAD.

Then, if <base_branch> has an authoritative docs/epics/index.md, reconciles
the local copy against it (guarded: only overwrites when the base's copy is
non-empty and looks like a real queue, protecting against a git hiccup
silently wiping the queue).

Outputs JSON: {"working_epic": "<epic>", "epic_branch": "feat/<epic>"}
On failure to create the branch, exits 1 and prints {"error": "..."} instead —
a failed checkout must halt the node, not silently report success while HEAD
stays wherever it was (the bug this replaces).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root

logger = logging.getLogger(__name__)

QUEUE_PATH = Path("docs/epics/index.md")
QUEUE_BULLET_RE = re.compile(r"^\s*[-*]\s+\[", re.MULTILINE)


def _git(args: list[str], root, *, echo: bool = False) -> subprocess.CompletedProcess:
    kwargs = dict(cwd=str(root), text=True, check=False)
    if echo:
        kwargs.update(stdout=sys.stderr, stderr=sys.stderr)
    else:
        kwargs.update(capture_output=True)
    return subprocess.run(["git", *args], **kwargs)


def branch_exists(branch: str, root) -> bool:
    return _git(["rev-parse", "--verify", "--quiet", branch], root).returncode == 0


def short_sha(branch: str, root) -> str:
    result = _git(["rev-parse", "--short", branch], root)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def archive_stale_branch(branch: str, root) -> None:
    """Rename an existing epic branch aside instead of resuming it. Renaming (not
    deleting) means the old work stays fully reachable under the archive name if
    anyone needs to dig it up later."""
    archive = f"archive/{branch[len('feat/'):]}-{short_sha(branch, root)}"
    if branch_exists(archive, root):
        # Same epic + same tip sha already archived (re-run at the exact same
        # commit) — don't clobber the existing archive; leave the stale branch
        # in place and let the checkout -b below fail loudly if feat/<epic> is
        # somehow still taken, rather than risk losing either ref.
        logger.warning("archive name %s already exists — leaving %s in place", archive, branch)
        return
    result = _git(["branch", "-m", branch, archive], root, echo=True)
    if result.returncode != 0:
        logger.warning("could not archive stale branch %s — leaving it in place", branch)
    else:
        logger.info("archived stale epic branch %s -> %s (renamed, not deleted)", branch, archive)


def reconcile_queue(root, base: str) -> None:
    if not base or not branch_exists(base, root):
        return
    if _git(["cat-file", "-e", f"{base}:{QUEUE_PATH}"], root).returncode != 0:
        return
    show = _git(["show", f"{base}:{QUEUE_PATH}"], root)
    content = show.stdout
    if show.returncode != 0 or not content.strip() or not QUEUE_BULLET_RE.search(content):
        return
    (root / QUEUE_PATH).write_text(content, encoding="utf-8")
    logger.info("reconciled index.md to %s", base)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else ""

    root = find_repo_root()

    _git(["checkout", "--", str(QUEUE_PATH)], root)

    if epic:
        branch = f"feat/{epic}"
        if branch_exists(branch, root):
            archive_stale_branch(branch, root)
        # Always cut fresh from current HEAD — even if archiving above left the old
        # branch in place (e.g. archive name collision), so a stale/diverged branch
        # is never silently reused. Exit code IS checked: an old, silent bug here
        # let a failed checkout report success while HEAD stayed put.
        result = _git(["checkout", "-b", branch], root, echo=True)
        if result.returncode != 0:
            print(json.dumps({"error": f"failed to create epic branch {branch}"}))
            sys.exit(1)

    reconcile_queue(root, base)

    print(json.dumps({"working_epic": epic, "epic_branch": f"feat/{epic}"}))


if __name__ == "__main__":
    main()
