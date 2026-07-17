#!/usr/bin/env python3
"""Select the current epic to work on — EPIC selection only (ostler-backed).

Epic-coder processes the epics queue (``docs/epics/index.md``, the OKF bundle index
that ostler manages) front-to-back, one PR per epic. This script returns the FRONT
epic of the queue as the current epic. Story selection within that epic is a SEPARATE
concern (see select-next-story.py).

The queue and the whole knowledge graph are now markdown owned by ``ostler`` (there is
no ``epics-todo.json``); this script reads the order via the in-process ostler API
(``Ostler.todo()``).

Pop-front-on-merge: once an epic's PR is merged the workflow calls prune-epic.py
(``todo prune``) to remove it from the front, so the next call here returns the
following epic.

Args: [<docs_path>]
Outputs JSON: {"has_epic": "yes"|"no", "epic": "<name>", "reason": "..."}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler
from workhorse.scriptutil import find_docs_root


def emit(**kwargs: str) -> NoReturn:
    payload = {"has_epic": "no", "epic": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _queue_from_ostler(okf: Ostler) -> list[str] | None:
    try:
        return [str(x) for x in okf.todo()]
    except (OSError, ValueError, RuntimeError):
        return None


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
    okf = Ostler(root)

    epics = _queue_from_ostler(okf)
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
