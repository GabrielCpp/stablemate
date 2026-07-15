#!/usr/bin/env python3
"""Final global coder-consumability validator — ostler-backed.

Confirms the whole ``docs/epics`` tree the author just produced is something the coder engine can
actually walk: a valid epics queue, every queued epic has its bookkeeping, and a first runnable
story is selectable. This is the last gate before the workflow reports success. Under the OKF
model the queue is the ostler-managed epics index (``ostler todo list``) and the story DAG folds
into each ``epic.md`` (``ostler list --type story --epic``) — there is no ``epics-todo.json`` /
``dependencies.json``.

  - the epics index lists ≥1 epic;
  - every listed epic has ``epic.md`` and ≥1 story in its ``## Stories``;
  - every listed story's ``story.md`` exists and has a ``- **Status**:`` line;
  - at least one story is selectable (status not already a done-state) — i.e. coder would have
    work to do.

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI.

Args:
    argv[1]  epics_dir : epics root (default docs/epics)

Outputs JSON: {"artifacts_ok": "yes"|"no", "artifacts_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_DONE_TOKENS = ("qa passed", "passed", "done", "merged", "complete")


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def ostler_json(root: Path, args: list[str], opener: str):
    ostler = shutil.which("ostler")
    if not ostler:
        return None
    try:
        proc = subprocess.run([ostler, *args], cwd=str(root), capture_output=True,
                              text=True, timeout=120)
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


def status_of(story_md: Path) -> str | None:
    if not story_md.is_file():
        return None
    for line in story_md.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- **Status**:"):
            return s.split(":", 1)[1].strip()
    return ""  # exists but no status line


def is_done(status: str) -> bool:
    s = (status or "").strip().lower()
    return any(tok in s for tok in _DONE_TOKENS)


def done(errors: list[str]) -> None:
    print(json.dumps({"artifacts_ok": "no" if errors else "yes",
                      "artifacts_errors": "\n".join(errors)}))
    sys.exit(0)


def main() -> None:
    epics_dir_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/epics"
    root = find_repo_root()
    epics_dir = root / epics_dir_rel

    queue = ostler_json(root, ["todo", "list", "--json"], "[")
    if queue is None:
        done(["could not read the epics index via `ostler todo list` (is ostler installed?)"])
    if not queue:
        done(["the epics index lists no epics"])

    errors: list[str] = []
    selectable = 0
    all_stories = ostler_json(root, ["list", "--type", "story", "--json"], "[") or []
    by_epic: dict[str, list[dict]] = {}
    for s in all_stories:
        by_epic.setdefault(str(s.get("epic", "")), []).append(s)

    for epic in queue:
        epic = str(epic)
        epic_dir = epics_dir / epic
        if not (epic_dir / "epic.md").is_file():
            errors.append(f"epic '{epic}': epic.md missing")
        stories = by_epic.get(epic, [])
        if not stories:
            errors.append(f"epic '{epic}': lists no stories in `## Stories`")
            continue
        for s in stories:
            slug = s.get("slug", "?")
            path = s.get("path", "")
            st = status_of(root / path) if path else None
            if st is None:
                errors.append(f"epic '{epic}' story '{slug}': story.md missing at {path or '<no path>'}")
            elif st == "":
                errors.append(f"epic '{epic}' story '{slug}': story.md has no `- **Status**:` line")
            elif not is_done(st):
                selectable += 1

    if selectable == 0 and not errors:
        errors.append("no selectable story (coder would have nothing to run)")

    done(errors)


if __name__ == "__main__":
    main()
