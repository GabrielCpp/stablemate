"""Whether a source a decision cites is there: a commit, a file at a commit, a file of the app or a page under a site the
book's documentation names."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ostler.book.service import Service
from ostler.book.sources import file_of, is_web, pointer_missing

COMMIT = re.compile(r"[0-9a-f]{7,40}")
COMMIT_FILE = re.compile(r"([0-9a-f]{7,40}):(.+)")


def commit_has(app: str, spec: str) -> bool:
    return subprocess.run(["git", "-C", app, "cat-file", "-e", spec], capture_output=True).returncode == 0


def source_is_there(pointer: str, app: str, members: dict[str, Path]) -> bool:
    if COMMIT.fullmatch(pointer):
        return commit_has(app, f"{pointer}^{{commit}}")
    named = COMMIT_FILE.fullmatch(pointer)
    if named:
        return commit_has(app, pointer)
    return not pointer_missing(file_of(pointer), app, members)


def under_site(service: Service[Any], pointer: str) -> bool:
    return service.documentation is not None and is_web(pointer) and pointer.startswith(service.documentation.sites)
