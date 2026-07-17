"""Resolve the denylist of private overlay project names.

stablemate is public. The private overlay's project names must not appear in it —
and neither must a denylist of those names, nor hashes of them, since either one
publishes the very words it exists to keep out. So the list is not in the tracked
tree at all. It is read, in order, from:

  1. ``$STABLEMATE_PRIVATE_NAMES`` — comma- or whitespace-separated.
  2. ``$GIT_DIR/private-names``   — one name per line; ``#`` starts a comment.

Both are untracked by construction: an env var is not a file, and ``.git/`` is
never part of a commit. A maintainer with the overlay drops the names in one of
them and gets the guard; a public contributor has neither and the guard is inert
(it cannot enforce a list nobody gave it).

Consumers: ``.githooks/pre-commit`` (blocks a leak at commit time, in staged changes
only) and ``scripts/check_public.py`` (the whole-tree sweep the hook cannot be — it
catches anything committed before the hook existed, or with ``--no-verify``).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ENV_VAR = "STABLEMATE_PRIVATE_NAMES"
GIT_FILE = "private-names"


def _git_dir() -> Path | None:
    """The repo's ``.git`` directory, or None outside a work tree."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out.stdout.strip())


def load() -> list[str]:
    """The configured private names, lowercased and deduplicated.

    Empty when neither source is configured — that is the public-contributor
    case, not an error.
    """
    raw = os.environ.get(ENV_VAR, "")
    if not raw.strip():
        git_dir = _git_dir()
        path = git_dir / GIT_FILE if git_dir else None
        if path and path.is_file():
            raw = path.read_text(encoding="utf-8")

    names: list[str] = []
    for line in raw.splitlines():
        for token in re.split(r"[,\s]+", line.split("#", 1)[0]):
            name = token.strip().lower()
            if name and name not in names:
                names.append(name)
    return names


def pattern(names: list[str]) -> re.Pattern[str] | None:
    """A case-insensitive alternation over ``names``, or None if there are none."""
    if not names:
        return None
    return re.compile("|".join(re.escape(name) for name in names), re.IGNORECASE)


if __name__ == "__main__":
    # `python3 scripts/private_names.py` prints one name per line — the shell
    # interface the pre-commit hook consumes. No names, no output, exit 0.
    for private_name in load():
        print(private_name)
    sys.exit(0)
