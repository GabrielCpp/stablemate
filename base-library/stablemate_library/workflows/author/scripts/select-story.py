#!/usr/bin/env python3
"""Select the next story in an epic whose story.md still needs writing — ostler-backed.

The story dependency-DAG now lives in the epic's ``epic.md`` (``## Stories``), not a
``dependencies.json`` — ostler reads it back. This selector asks ostler for the epic's
stories (``Ostler(root).list("story", epic=<epic>)``), topologically sorts them by their
``dependsOn`` edges (the same order coder executes them in), and returns the first story
whose ``story.md`` is missing OR has no ``- **Status**:`` line yet (a placeholder/empty
file from a partial run). When every story has a real ``story.md``, ``has_story`` is
``"no"`` and the workflow proceeds to epic-coverage validation.

Full rubric validation is the ``validate_story`` node's job; this selector only advances
the loop, so a freshly written story is validated (and reworked if needed) before the loop
comes back here and skips it.

Stdlib-only except for the in-process ``ostler`` Python API (``from ostler import Ostler``).

Args:
    argv[1]  epic_dir : repo-relative epic folder (e.g. docs/epics/<epic>)

Outputs JSON: {"has_story": "yes"|"no", "story_path": "...", "story_slug": "...",
               "story_dir": "...", "reason": "..."}
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


def topo(stories: list[dict]) -> list[dict]:
    by_slug = {s.get("slug"): s for s in stories if s.get("slug")}
    order: list[str] = []
    seen: set[str] = set()
    temp: set[str] = set()

    def visit(slug: str) -> None:
        if slug in seen or slug in temp:
            return
        temp.add(slug)
        for dep in by_slug.get(slug, {}).get("dependsOn", []):
            if dep in by_slug:
                visit(dep)
        temp.discard(slug)
        seen.add(slug)
        order.append(slug)

    for s in stories:
        if s.get("slug"):
            visit(s["slug"])
    return [by_slug[slug] for slug in order]


def has_status_line(story_md: Path) -> bool:
    if not story_md.is_file():
        return False
    for line in story_md.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("- **Status**:"):
            return True
    return False


def emit(**kwargs: str) -> NoReturn:
    payload = {"has_story": "no", "story_path": "", "story_slug": "", "story_dir": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    epic_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not epic_dir_rel:
        emit(reason="no epic_dir supplied")
    epic = Path(epic_dir_rel).name
    root = find_repo_root()
    okf = Ostler(root)

    try:
        stories = okf.list("story", epic=epic)
    except (OSError, ValueError, RuntimeError):
        emit(reason=f"could not read stories for epic '{epic}' via ostler's in-process API")
    if not stories:
        emit(reason="epic lists no stories yet — story-split must populate `## Stories`")

    for story in topo(stories):
        slug = story.get("slug", "")
        path = story.get("path", "")
        if not slug or not path:
            continue
        story_md = root / path
        if not has_status_line(story_md):
            emit(
                has_story="yes",
                story_path=path,
                story_slug=slug,
                story_dir=str(Path(path).parent),
                reason="story.md missing or has no `- **Status**:` line yet",
            )

    emit(reason="every story in the epic has a written story.md")


if __name__ == "__main__":
    main()
