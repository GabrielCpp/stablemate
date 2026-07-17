#!/usr/bin/env python3
"""Decide whether the granularity planner needs to run at all.

Two things beat the planner, in order (the same precedence idiom as research's
program selection):

1. **A frozen inventory.** If ``inventory.json`` already exists, a prior run (or a
   mid-run resume) materialized the unit list; the survey MUST consume that exact
   list and never re-plan — a resume that produced a *different* list would silently
   break the coverage claim. ``expand-inventory.py`` enforces the freeze; this node
   only routes around the planner.
2. **Operator-pinned rules.** If the rules file exists (hand-written, or committed by
   a prior run), expansion uses it verbatim — for the day the planner misjudges a
   repo and the operator wants to pin the enumeration without editing prompts.

Only when neither exists does the planner get its one bounded judgment.

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  inventory : repo-relative path to inventory.json
    argv[2]  rules     : repo-relative path to the enumeration-rules file

Outputs JSON: {"needs_plan": "yes"|"no", "check_note": "<why>"}
"""
from __future__ import annotations

import json
import logging
import os
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


def main(logger: logging.Logger) -> None:
    inventory_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/inventory.json"
    rules_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/units.yml"

    root = find_repo_root()
    if (root / inventory_rel).is_file():
        note = f"inventory {inventory_rel} already exists — frozen; the planner never re-runs"
        logger.info(note)
    elif (root / rules_rel).is_file():
        note = f"rules {rules_rel} already exist (operator-pinned or prior run) — planner skipped"
        logger.info(note)
    else:
        logger.info("no inventory or rules yet — the planner decides the enumeration rules")
        print(json.dumps({"needs_plan": "yes", "check_note": "no inventory or rules yet — the planner decides the enumeration rules"}))
        return
    print(json.dumps({"needs_plan": "no", "check_note": note}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("check-inventory"))
