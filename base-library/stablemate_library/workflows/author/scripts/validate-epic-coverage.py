#!/usr/bin/env python3
"""Deterministic epic-coverage validator — ostler-backed, strictly epic-scoped.

The structural checks (every seed covered by a story, stories form an acyclic graph within the
epic, no cross-epic seed/dependency references, every story has a story.md) are exactly what
``ostler.doctor(epic=<epic>)`` computes — and crucially, ostler scopes its findings to the named
epic, so this gate can no longer evaluate the *wrong* epic's seeds/stories (the cross-epic routing
bug). On top of that we keep the **deferral-ownership** invariant: every knowledge gap marked
``disposition: deferred`` must name an owner that resolves to a real story slug, a seed id, or an
open backlog item — checked against the whole graph via ostler.

Args:
    argv[1]  epic_dir : repo-relative epic folder (docs/epics/<epic>); the basename is the epic.

Outputs JSON: {"coverage_ok": "yes"|"no", "coverage_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
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


def _backlog_ids(okf: Ostler) -> set[str]:
    return {str(r.get("id", "")).strip() for r in okf.backlog() if r.get("id")}


def main() -> None:
    epic_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not epic_dir_rel:
        print(json.dumps({"coverage_ok": "no", "coverage_errors": "no epic_dir supplied"}))
        return
    epic = Path(epic_dir_rel).name
    root = find_repo_root()
    okf = Ostler(root)
    errors: list[str] = []

    try:
        report = okf.doctor(epic=epic)
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"coverage_ok": "no",
                          "coverage_errors": f"ostler doctor for epic {epic} could not run"}))
        return
    for f in report.get("findings", []):
        if f.get("severity") == "error" and f.get("code") in _COVERAGE_CODES:
            errors.append(f"[{f.get('code')}] {f.get('message')}")

    # deferral ownership: every deferred gap names an owner that resolves anywhere in the graph
    gaps = okf.list("gap")
    deferred = [g for g in gaps if str(g.get("disposition", "")).strip() == "deferred"]
    if deferred:
        slugs = {s.get("slug") for s in okf.list("story")}
        seeds = {s.get("id") for s in okf.list("seed")}
        universe = {x for x in (slugs | seeds) if x} | _backlog_ids(okf)
        for g in deferred:
            owner = str(g.get("owner", "")).strip()
            gid, surface = g.get("id", "?"), g.get("surface", "?")
            if not owner:
                errors.append(f"deferred gap '{gid}' in {surface} names no owner")
            elif owner not in universe:
                errors.append(f"deferred gap '{gid}' in {surface} names owner '{owner}' that "
                              f"resolves to no story slug, seed id, or open backlog item")

    print(json.dumps({"coverage_ok": "no" if errors else "yes",
                      "coverage_errors": "\n".join(errors)}))


if __name__ == "__main__":
    main()
