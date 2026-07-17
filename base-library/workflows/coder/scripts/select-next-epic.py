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
import logging
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


def main(logger: logging.Logger) -> None:
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
        logger.warning("could not read the epics queue (ostler todo list)")
        emit(reason="could not read the epics queue (ostler todo list)")
    if not epics:
        logger.info("epic queue is empty — every epic has been merged")
        emit(reason="epic queue is empty — every epic has been merged")

    logger.info("selected epic '%s'", epics[0])
    emit(has_epic="yes", epic=str(epics[0]))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-next-epic"))
