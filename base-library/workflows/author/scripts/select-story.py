#!/usr/bin/env python3
"""Select the next story in an epic whose story.md still needs writing — ostler-backed.

The story dependency-DAG lives in the epic's ``epic.md`` (``## Stories``), not a
``dependencies.json``. **ostler answers the whole question**: ``Ostler.next_story_report(epic,
need="author")`` walks that DAG in dependency order — the order coder builds in — and returns the
first story that is not *authored*, i.e. whose ``story.md`` is missing or whose required sections
(``registry.STORY_SECTIONS``) are still empty. When every story is written the report's state is
``done``, ``has_story`` is ``"no"``, and the workflow proceeds to epic-coverage validation.

This script does not open a ``story.md`` and does not define "written" for itself. It used to:
it selected on the presence of a ``- **Status**:`` line, which ``ostler create story`` writes into
every scaffold — so every story was born "done", the loop routed straight past ``write_story``, and
a run produced 44 empty stories and reported success. One definition of authored, owned by the
graph's owner, is the fix.

Full rubric validation is the ``validate_story`` node's job; this selector only advances the loop,
so a freshly written story is validated (and reworked if needed) before the loop comes back here
and skips it.

Selection runs through the shared ``workhorse.worklist`` primitive: the DAG-ordered stories are a
worklist whose *done* items are the authored ones, so ``select_next`` returns the first not-done
story — the same pick as the report — and its ``snapshot`` gives the dashboard the "3/12 authored"
progress the run had no way to show.

Stdlib-only except for the in-process ``ostler`` Python API (``from ostler import Ostler``).

Args:
    argv[1]  epic_dir : repo-relative epic folder (e.g. docs/epics/<epic>)

Outputs JSON: {"has_story": "yes"|"no", "story_path": "...", "story_slug": "...",
               "story_dir": "...", "reason": "...", "progress": "...",
               "remaining_count": "..."}
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
    payload = {"has_story": "no", "story_path": "", "story_slug": "", "story_dir": "",
               "reason": "", "progress": "", "remaining_count": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    epic_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not epic_dir_rel:
        logger.warning("no epic_dir supplied")
        emit(reason="no epic_dir supplied")
    epic = Path(epic_dir_rel).name
    okf = Ostler(find_repo_root())

    try:
        report = okf.next_story_report(epic, need="author")
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read stories for epic '%s' via ostler's in-process API", epic)
        emit(reason=f"could not read stories for epic '{epic}' via ostler's in-process API")

    # `state` distinguishes "nothing left to write" from "there was never anything to write" —
    # an absent story is not a finished one, so an epic with no `## Stories` must route back to
    # story-split rather than read as authored.
    if report["state"] in ("no-epic", "no-stories"):
        logger.info("%s", report["detail"])
        emit(reason=report["detail"])

    # The report's own tallies are the worklist: `done` stories are authored, `remaining` are the
    # unwritten ones, in DAG order. Feeding them to the shared primitive keeps the dashboard's
    # "3/12" identical in shape to every other worklist node in the library.
    items = ([{"id": f"authored-{i}", "status": "done"} for i in range(int(report["done"]))]
             + [{"id": slug, "status": "pending"} for slug in report["remaining"]])
    snap = wl.snapshot(items)

    if report["state"] != "ready":
        logger.info("every story in epic '%s' has a written story.md", epic)
        emit(reason=report["detail"],
             progress=snap["progress"], remaining_count=str(snap["remaining"]))

    story = report["story"]
    slug, path = str(story.get("slug", "")), str(story.get("path", ""))
    logger.info("selected story '%s' — %s", slug, report["detail"])
    emit(
        has_story="yes",
        story_path=path,
        story_slug=slug,
        story_dir=str(Path(path).parent),
        reason=report["detail"],
        progress=snap["progress"],
        remaining_count=str(snap["remaining"]),
    )


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-story"))
