#!/usr/bin/env python3
"""`git init` the genesis target and land one initial commit. Runs before anything else.

**This must be the first mutating node in the flow**, and the ordering is load-bearing rather
than stylistic. ``ostler.model.find_root`` walks *up* from its starting directory looking for
``.git``, ``docs/``, ``ostler.yml``, or ``agents.yml``. A brand-new directory has none of
them — so every ostler call made before this node binds to whichever **ancestor** repo happens
to be above the target, silently. Ids get allocated out of the parent's ``.agents/ids.json``,
``docs/*`` paths resolve into the parent's tree, and nothing errors. The run looks fine and
writes into the wrong repository.

Creating ``.git`` first gives ``find_root`` a boundary to stop at, which closes that off
structurally. ``validate-genesis.py`` then asserts the binding actually landed where intended,
because a misbind is exactly the failure a benchmark cannot detect after the fact.

The initial commit matters too: an unborn HEAD has no commit for a branch to point at, and
the author workflow's ``branch-author.py`` cuts a branch as one of its first acts.

Local-only by design — no remote is added. PR delivery is optional downstream
(``open-author-pr.py`` skips cleanly when no forge is configured).

Args:
    argv[1]  target_dir   : absolute path to the repo (from resolve-genesis-target.py)
    argv[2]  target_state : "absent" | "partial" | "existing"

Outputs JSON: {"git_ready": "yes"|"no", "git_note": "<line>", "initial_commit": "<sha>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

logger = logging.getLogger(__name__)


def emit(**kwargs) -> NoReturn:
    payload = {"git_ready": "no", "git_note": "", "initial_commit": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def git(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(target), capture_output=True,
                          text=True, check=False, timeout=30)


def head_sha(target: Path) -> str:
    result = git(target, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def main(logger: logging.Logger) -> None:
    target_arg = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not target_arg:
        emit(git_note="no target_dir was provided")

    target = Path(target_arg)
    target.mkdir(parents=True, exist_ok=True)

    if (target / ".git").exists():
        sha = head_sha(target)
        if sha:
            logger.info("%s is already a git repo at %s", target, sha[:8])
            emit(git_ready="yes", initial_commit=sha,
                 git_note=f"already a git repo (HEAD {sha[:8]})")
        # A .git with an unborn HEAD still needs the initial commit below.
        logger.info("%s has .git but an unborn HEAD — landing the initial commit", target)
    else:
        result = git(target, "init", "-q")
        if result.returncode != 0:
            emit(git_note=f"git init failed: {result.stderr.strip()}")

    # A commit needs *something* tracked. A README is the least surprising choice and is
    # the file a human opening the new repo looks for first.
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(f"# {target.name}\n", encoding="utf-8")

    git(target, "add", "-A")
    result = git(target, "commit", "-q", "-m", "Initial commit")
    if result.returncode != 0 and not head_sha(target):
        emit(git_note=f"initial commit failed: {(result.stderr or result.stdout).strip()}")

    sha = head_sha(target)
    logger.info("initialised %s at %s", target, sha[:8])
    emit(git_ready="yes", initial_commit=sha,
         git_note=f"git initialised with an initial commit ({sha[:8]}), no remote configured")


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("genesis-git-init"))
