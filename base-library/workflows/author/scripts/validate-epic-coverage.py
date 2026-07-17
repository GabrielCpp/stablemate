#!/usr/bin/env python3
"""Deterministic epic-coverage validator — ostler-backed, strictly epic-scoped.

The structural checks (every seed covered by a story, stories form an acyclic graph within the
epic, no cross-epic seed/dependency references, every story has a story.md) are exactly what
``ostler.doctor(epic=<epic>)`` computes — and crucially, ostler scopes its findings to the named
epic, so this gate can no longer evaluate the *wrong* epic's seeds/stories (the cross-epic routing
bug).

Args:
    argv[1]  epic_dir : repo-relative epic folder (docs/epics/<epic>); the basename is the epic.

Outputs JSON: {"coverage_ok": "yes"|"no", "coverage_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from ostler import Ostler

# error finding codes from `ostler doctor` that mean the epic's coverage/graph is broken
_COVERAGE_CODES = {
    "orphan-seed", "dangling-seed", "cross-epic-seed",
    "dangling-dependency", "cross-epic-dependency", "missing-story-file",
}


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
    epic_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not epic_dir_rel:
        logger.warning("no epic_dir supplied")
        print(json.dumps({"coverage_ok": "no", "coverage_errors": "no epic_dir supplied"}))
        return
    epic = Path(epic_dir_rel).name
    root = find_repo_root()
    okf = Ostler(root)
    errors: list[str] = []

    try:
        report = okf.doctor(epic=epic)
    except (OSError, ValueError, RuntimeError):
        logger.warning("ostler doctor for epic %s could not run", epic)
        print(json.dumps({"coverage_ok": "no",
                          "coverage_errors": f"ostler doctor for epic {epic} could not run"}))
        return
    for f in report.get("findings", []):
        if f.get("severity") == "error" and f.get("code") in _COVERAGE_CODES:
            errors.append(f"[{f.get('code')}] {f.get('message')}")

    logger.info("epic '%s' coverage: %d error(s)", epic, len(errors))
    print(json.dumps({"coverage_ok": "no" if errors else "yes",
                      "coverage_errors": "\n".join(errors)}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-epic-coverage"))
