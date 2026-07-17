#!/usr/bin/env python3
"""Select the next epic that still needs authoring (the per-epic loop driver) — ostler-backed.

Walks the epics queue (``docs/epics/index.md``, owned by ostler) in order and returns the first
epic whose authoring is not yet complete. "Complete" means the epic has ``epic.md`` AND lists at
least one story (in ``## Stories``) AND every listed story has a ``story.md`` on disk. There is no
``seed.json`` / ``dependencies.json`` / ``epics-todo.json`` — seeds and the story DAG live in
``epic.md`` and ostler reads them back.

Commands the OKF graph through the in-process ``ostler`` Python API (the library
face of the CLI) instead of shelling out.

Args:
    argv[1]  epics_dir : epics root (default docs/epics)

Outputs JSON: {"has_epic": "yes"|"no", "epic": "...", "epic_dir": "...", "reason": "..."}
"""
from __future__ import annotations

import json
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


def emit(**kwargs: str) -> NoReturn:
    payload = {"has_epic": "no", "epic": "", "epic_dir": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    epics_dir_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/epics"
    okf = Ostler(find_repo_root())

    try:
        queue = okf.todo()
        stories = okf.list("story")
    except (OSError, ValueError, RuntimeError):
        emit(reason="could not read the epics queue via `ostler todo list`")
    root = okf.root

    if not queue:
        # no index yet → the epic-split stage must create epics (and queue them)
        emit(reason="epics queue is empty — the epic-split stage must create + queue epics")

    by_epic: dict[str, list[dict]] = {}
    for s in stories:
        by_epic.setdefault(s.get("epic", ""), []).append(s)

    for epic in queue:
        epic = str(epic)
        epic_dir = root / epics_dir_rel / epic
        epic_stories = by_epic.get(epic, [])
        complete = (epic_dir / "epic.md").is_file() and bool(epic_stories) and all(
            st.get("path") and (root / st["path"]).is_file() for st in epic_stories
        )
        if not complete:
            emit(
                has_epic="yes",
                epic=epic,
                epic_dir=f"{epics_dir_rel}/{epic}",
                reason="epic missing epic.md, has no stories, or a story.md is absent",
            )

    emit(reason="every epic in the queue is fully authored")


if __name__ == "__main__":
    main()
