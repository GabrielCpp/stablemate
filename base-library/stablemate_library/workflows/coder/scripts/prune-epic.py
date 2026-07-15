#!/usr/bin/env python3
"""Pop a merged epic off the front of the queue (pop-front-on-merge) — ostler-backed.

Called after an epic's PR has been gated + merged (or passed through offline). The epics queue is
now the ostler-managed OKF index ``docs/epics/index.md`` (there is no ``epics-todo.json``), so this
removes the named epic via ``ostler todo prune <epic>`` and ``select-next-epic.py`` returns the
following epic on the next iteration. Idempotent and best-effort: a missing index, an absent epic,
or a write failure is not fatal — a stale entry only costs one extra no-op PR/merge cycle.

Back-compat: if an explicit JSON queue path is passed as argv[2] (a runtime sidecar), this pops
the epic from that JSON array instead — mirroring select-next-epic.py's sidecar precedence.

Args:
    argv[1]  epic : the epic to remove (the just-merged one)
    argv[2]  todo : optional explicit queue path (JSON sidecar); empty → ostler index.md

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI.

Outputs JSON: {"pruned": "yes"|"no"}
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


def emit(pruned: str) -> None:
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


def _prune_ostler(root: Path, epic: str) -> str:
    ostler = shutil.which("ostler")
    if not ostler:
        return "no"
    try:
        proc = subprocess.run([ostler, "todo", "prune", epic], cwd=str(root),
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "no"
    return "yes" if proc.returncode == 0 else "no"


def main() -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    if not epic:
        emit("no")

    root = find_repo_root()

    # An explicit sidecar path (argv[2]) wins, matching select-next-epic.py's precedence.
    if len(sys.argv) > 2 and sys.argv[2].strip():
        p = Path(sys.argv[2])
        if not p.is_absolute():
            p = root / p
        emit(_prune_json_sidecar(p, epic))

    # Try ostler first; fall back to the legacy epics-todo.json if ostler is unavailable
    # or the epic isn't in the ostler-managed queue (mirrors select-next-epic.py's fallback).
    if _prune_ostler(root, epic) == "yes":
        emit("yes")
    default_json = root / "docs" / "epics" / "epics-todo.json"
    emit(_prune_json_sidecar(default_json, epic))


if __name__ == "__main__":
    main()
