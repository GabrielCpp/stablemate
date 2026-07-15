#!/usr/bin/env python3
"""Select the current epic to work on — EPIC selection only (ostler-backed).

Epic-coder processes the epics queue (``docs/epics/index.md``, the OKF bundle index
that ostler manages) front-to-back, one PR per epic. This script returns the FRONT
epic of the queue as the current epic. Story selection within that epic is a SEPARATE
concern (see select-next-story.py).

The queue and the whole knowledge graph are now markdown owned by ``ostler`` (there is
no ``epics-todo.json``); this script shells out to ``ostler todo list`` for the order.

Pop-front-on-merge: once an epic's PR is merged the workflow calls prune-epic.py
(``ostler todo prune``) to remove it from the front, so the next call here returns the
following epic.

Args: [<docs_path>]
Outputs JSON: {"has_epic": "yes"|"no", "epic": "<name>", "reason": "..."}
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def emit(**kwargs: str) -> None:
    payload = {"has_epic": "no", "epic": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _queue_from_ostler(root: Path) -> list[str] | None:
    ostler = shutil.which("ostler")
    if not ostler:
        return None
    try:
        proc = subprocess.run([ostler, "-C", str(root), "todo", "list", "--json"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (proc.stdout or "").strip()
    start = raw.find("[")
    if start == -1:
        return []
    try:
        data = json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None
    return [str(x) for x in data] if isinstance(data, list) else None


def _queue_from_json(root: Path) -> list[str] | None:
    """Fallback: read the legacy epics-todo.json queue file."""
    todo = root / "docs" / "epics" / "epics-todo.json"
    if not todo.is_file():
        return None
    try:
        data = json.loads(todo.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return [str(x) for x in data] if isinstance(data, list) else None


def main() -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    root = find_docs_root(docs_path_arg)

    epics = _queue_from_ostler(root)
    if epics is None or (not epics and _queue_from_json(root) is not None):
        # ostler unavailable or returned empty but a legacy epics-todo.json exists —
        # fall back to the JSON file so test sandboxes and legacy repos still work.
        json_epics = _queue_from_json(root)
        if json_epics is not None:
            epics = json_epics
    if epics is None:
        emit(reason="could not read the epics queue (ostler todo list)")
    if not epics:
        emit(reason="epic queue is empty — every epic has been merged")

    emit(has_epic="yes", epic=str(epics[0]))


if __name__ == "__main__":
    main()
