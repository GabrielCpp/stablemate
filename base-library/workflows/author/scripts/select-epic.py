#!/usr/bin/env python3
"""Select the next epic that still needs authoring (the per-epic loop driver) — ostler-backed.

Walks the epics queue (``docs/epics/index.md``, owned by ostler) in order and returns the first
epic whose authoring is not yet complete. **ostler owns that verdict** — ``Ostler.epic_authored``:
the epic has ``epic.md``, lists at least one story (in ``## Stories``), and every listed story has a
*written* ``story.md`` (its required sections carry prose, per ``registry.STORY_SECTIONS``). This
script does not open a story file or define "authored" for itself; a story.md that merely exists is
a scaffold, not authoring. There is no ``seed.json`` / ``dependencies.json`` / ``epics-todo.json`` —
seeds and the story DAG live in ``epic.md`` and ostler reads them back.

Commands the OKF graph through the in-process ``ostler`` Python API (the library
face of the CLI) instead of shelling out. Selection runs through the shared
``workhorse.worklist`` primitive: the queue is a worklist whose *done* epics are the
ones ostler reports authored, so ``select_next`` returns the first not-done epic — the old
front-not-complete rule — and its ``snapshot`` gives the dashboard epic progress.

Args:
    argv[1]  epics_dir : epics root (default docs/epics)

Outputs JSON: {"has_epic": "yes"|"no", "epic": "...", "epic_dir": "...", "reason": "...",
               "progress": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler
from workhorse import worklist as wl


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(**kwargs: str) -> NoReturn:
    payload = {"has_epic": "no", "epic": "", "epic_dir": "", "reason": "", "progress": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    epics_dir_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/epics"
    okf = Ostler(find_repo_root())

    try:
        queue = okf.todo()
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read the epics queue via `ostler todo list`")
        emit(reason="could not read the epics queue via `ostler todo list`")

    if not queue:
        # no index yet → the epic-split stage must create epics (and queue them)
        logger.info("epics queue is empty — the epic-split stage must create + queue epics")
        emit(reason="epics queue is empty — the epic-split stage must create + queue epics")

    # The queue is a worklist: an epic is *done* once ostler says it is authored — epic.md
    # present, ≥1 story, and every story.md actually written. That verdict is ostler's alone
    # (`Story.authored` over `registry.STORY_SECTIONS`); this script must not re-derive it from
    # the filesystem. It used to, by testing that each story.md *existed*, which a bare
    # scaffold satisfies — so an epic of 44 empty stories read as fully authored and a rerun
    # ended immediately with `has_epic=no` instead of going back to finish the work.
    # Items stay in queue order (no `order` key → sequence order preserved), so select_next
    # returns the front not-done epic and the snapshot counts authored epics for the dashboard.
    items = [{"id": str(epic),
              "status": "done" if okf.epic_authored(str(epic)) else "pending"}
             for epic in queue]

    snap = wl.snapshot(items)
    pick = wl.select_next(items)
    if pick is None:
        logger.info("every epic in the queue is fully authored")
        emit(reason="every epic in the queue is fully authored", progress=snap["progress"])

    epic = str(pick["id"])
    logger.info("selected epic '%s' — missing epic.md, has no stories, or a story is unwritten", epic)
    emit(
        has_epic="yes",
        epic=epic,
        epic_dir=f"{epics_dir_rel}/{epic}",
        reason="epic missing epic.md, has no stories, or a story is still unwritten",
        progress=snap["progress"],
    )


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-epic"))
