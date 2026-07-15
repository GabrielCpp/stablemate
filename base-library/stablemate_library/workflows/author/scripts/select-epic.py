#!/usr/bin/env python3
"""Select the next epic that still needs authoring (the per-epic loop driver) — ostler-backed.

Walks the epics queue (``docs/epics/index.md``, owned by ostler) in order and returns the first
epic whose authoring is not yet complete. "Complete" means the epic has ``epic.md`` AND lists at
least one story (in ``## Stories``) AND every listed story has a ``story.md`` on disk. There is no
``seed.json`` / ``dependencies.json`` / ``epics-todo.json`` — seeds and the story DAG live in
``epic.md`` and ostler reads them back.

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI.

Args:
    argv[1]  epics_dir : epics root (default docs/epics)

Outputs JSON: {"has_epic": "yes"|"no", "epic": "...", "epic_dir": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(**kwargs: str) -> None:
    payload = {"has_epic": "no", "epic": "", "epic_dir": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def ostler_json(root: Path, args: list[str], opener: str):
    ostler = shutil.which("ostler")
    if not ostler:
        return None
    try:
        proc = subprocess.run([ostler, *args], cwd=str(root), capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (proc.stdout or "").strip()
    start = raw.find(opener)
    if start == -1:
        return [] if opener == "[" else None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def main() -> None:
    epics_dir_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/epics"
    root = find_repo_root()

    queue = ostler_json(root, ["todo", "list", "--json"], "[")
    if queue is None:
        emit(reason="could not read the epics queue via `ostler todo list`")
    if not queue:
        # no index yet → the epic-split stage must create epics (and queue them)
        emit(reason="epics queue is empty — the epic-split stage must create + queue epics")

    stories = ostler_json(root, ["list", "--type", "story", "--json"], "[") or []
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
