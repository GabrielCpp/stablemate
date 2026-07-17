#!/usr/bin/env python3
"""Pop a merged epic off the front of the queue (pop-front-on-merge) — ostler-backed.

Called after an epic's PR has been gated + merged (or passed through offline). The epics queue is
now the ostler-managed OKF index ``docs/epics/index.md`` (there is no ``epics-todo.json``), so this
removes the named epic via the in-process ostler ``todo_prune`` API and ``select-next-epic.py`` returns the
following epic on the next iteration. Idempotent and best-effort: a missing index, an absent epic,
or a write failure is not fatal — a stale entry only costs one extra no-op PR/merge cycle.

Back-compat: if an explicit JSON queue path is passed as argv[2] (a runtime sidecar), this pops
the epic from that JSON array instead — mirroring select-next-epic.py's sidecar precedence.

Args:
    argv[1]  epic : the epic to remove (the just-merged one)
    argv[2]  todo : optional explicit queue path (JSON sidecar); empty → ostler index.md

Stdlib-only except for the in-process ``ostler`` Python API.

Outputs JSON: {"pruned": "yes"|"no"}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(pruned: str) -> NoReturn:
    print(json.dumps({"pruned": pruned}))
    sys.exit(0)


def _prune_json_sidecar(todo_path: Path, epic: str) -> str:
    """Back-compat: pop the epic from an explicit JSON queue array."""
    if not todo_path.is_file():
        return "no"
    try:
        epics = json.loads(todo_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "no"
    if not isinstance(epics, list) or epic not in epics:
        return "no"
    epics.remove(epic)  # first occurrence (the front, in normal pop-front operation)
    try:
        todo_path.write_text(json.dumps(epics, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return "no"
    return "yes"


def _prune_ostler(okf: Ostler, epic: str) -> str:
    try:
        res = okf.todo_prune(epic)
    except (OSError, ValueError, RuntimeError):
        return "no"
    return "yes" if res.ok else "no"


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    if not epic:
        logger.info("no epic given — nothing to prune")
        emit("no")

    root = find_repo_root()

    # An explicit sidecar path (argv[2]) wins, matching select-next-epic.py's precedence.
    if len(sys.argv) > 2 and sys.argv[2].strip():
        p = Path(sys.argv[2])
        if not p.is_absolute():
            p = root / p
        logger.info("explicit sidecar %s given — pruning '%s' from it", p, epic)
        emit(_prune_json_sidecar(p, epic))

    # Try ostler first; fall back to the legacy epics-todo.json if ostler is unavailable
    # or the epic isn't in the ostler-managed queue (mirrors select-next-epic.py's fallback).
    try:
        okf = Ostler(root)
        pruned = _prune_ostler(okf, epic)
    except (OSError, ValueError, RuntimeError):
        pruned = "no"
    if pruned == "yes":
        logger.info("pruned '%s' via the ostler-managed epics queue", epic)
        emit("yes")
    logger.info("'%s' not found via ostler — falling back to epics-todo.json", epic)
    default_json = root / "docs" / "epics" / "epics-todo.json"
    emit(_prune_json_sidecar(default_json, epic))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("prune-epic"))
