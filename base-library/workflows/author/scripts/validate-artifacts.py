#!/usr/bin/env python3
"""Final global coder-consumability validator — ostler-backed.

Confirms the whole ``docs/epics`` tree the author just produced is something the coder engine can
actually walk: a valid epics queue, every queued epic has its bookkeeping, and a first runnable
story is selectable. This is the last gate before the workflow reports success. Under the OKF
model the queue is the ostler-managed epics index (``okf.todo()``) and the story DAG folds
into each ``epic.md`` (``okf.list("story")``) — there is no ``epics-todo.json`` /
``dependencies.json``.

  - the epics index lists ≥1 epic;
  - every listed epic has ``epic.md`` (ostler can load it) and ≥1 story in its ``## Stories``;
  - every listed story is **authored** — ostler's verdict (``story.md`` exists and its required
    sections carry prose, per ``registry.STORY_SECTIONS``), not "the file is there";
  - at least one story is selectable (status not already a done-state) — i.e. coder would have
    work to do.

This gate used to accept a story.md that merely existed and carried a ``- **Status**:`` line —
both of which ``ostler create story`` writes into the scaffold. So a queue of 44 empty stubs
passed here, the run reported success and opened a PR. An unauthored story is now an error that
names the epic, the slug and the empty sections, and it does not count toward ``selectable``.

Stdlib-only except for the in-process ``ostler`` Python API (``from ostler import Ostler``).

Args:
    argv[1]  epics_dir : epics root — accepted for the node's contract but unused; ostler
                         discovers the graph's doc roots itself.

Outputs JSON: {"artifacts_ok": "yes"|"no", "artifacts_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler

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


def is_done(status: str) -> bool:
    s = (status or "").strip().lower()
    return any(tok in s for tok in _DONE_TOKENS)


def done(errors: list[str]) -> NoReturn:
    print(json.dumps({"artifacts_ok": "no" if errors else "yes",
                      "artifacts_errors": "\n".join(errors)}))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    okf = Ostler(find_repo_root())

    try:
        queue = okf.todo()
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read the epics index via ostler's in-process API")
        done(["could not read the epics index via ostler's in-process API"])
    if not queue:
        logger.info("the epics index lists no epics")
        done(["the epics index lists no epics"])

    errors: list[str] = []
    selectable = 0
    all_stories = okf.list("story")
    by_epic: dict[str, list[dict]] = {}
    for s in all_stories:
        by_epic.setdefault(str(s.get("epic", "")), []).append(s)

    # An epic ostler could not load has no epic.md — the graph's own answer, so this script
    # never stats a file and never gets a second opinion about what a document must contain.
    loadable = {e.name for e in okf.graph.epics}

    for epic in queue:
        epic = str(epic)
        if epic not in loadable:
            errors.append(f"epic '{epic}': epic.md missing (ostler cannot load the epic)")
        stories = by_epic.get(epic, [])
        if not stories:
            errors.append(f"epic '{epic}': lists no stories in `## Stories`")
            continue
        for s in stories:
            slug = s.get("slug", "?")
            path = s.get("path", "")
            if not s.get("hasStoryMd"):
                errors.append(f"epic '{epic}' story '{slug}': story.md missing at {path or '<no path>'}")
            elif not s.get("authored"):
                empty = ", ".join(s.get("unwrittenSections") or []) or "its required sections"
                errors.append(f"epic '{epic}' story '{slug}': story.md is still a bare scaffold "
                              f"({empty} empty) at {path}")
            elif not is_done(str(s.get("status", ""))):
                selectable += 1

    if selectable == 0 and not errors:
        errors.append("no selectable story (coder would have nothing to run)")

    logger.info("artifacts validation: %d error(s), %d selectable stor(y/ies)", len(errors), selectable)
    done(errors)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-artifacts"))
