"""Resolve the denylist of private overlay project names."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ENV_VAR = "STABLEMATE_PRIVATE_NAMES"
GIT_FILE = "private-names"
WAIVER_FILE = "private-names-waivers.json"


def _git_dir() -> Path | None:
    """The repo's main ``.git`` directory, or None outside a work tree."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out.stdout.strip())


def load() -> list[str]:
    """The configured private names, lowercased and deduplicated."""
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


def load_waivers() -> dict[str, dict[str, dict[str, str]]]:
    """The waived history hits, keyed by kind then full SHA."""
    git_dir = _git_dir()
    path = git_dir / WAIVER_FILE if git_dir else None
    data = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else {}
    return {"commit_messages": dict(data.get("commit_messages", {}))}


def pattern(names: list[str]) -> re.Pattern[str] | None:
    """A case-insensitive alternation over ``names``, or None if there are none."""
    if not names:
        return None
    return re.compile("|".join(re.escape(name) for name in names), re.IGNORECASE)


if __name__ == "__main__":
    for private_name in load():
        print(private_name)
    sys.exit(0)
