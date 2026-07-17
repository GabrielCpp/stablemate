#!/usr/bin/env python3
"""okf-builder walkthrough: seed the walk worklist from the documented journeys.

Journeys are the unit of the walk: each ``flow`` doc's ``start:``/``steps:`` is the
script a real user follows, so the agent reaches every screen *along a journey*
rather than by jumping to a URL. We seed one ``journey`` item per ``flow`` doc for
this service (found with ``ostler search``); screens are visited as journeys
traverse them, and any screen a journey cannot reach surfaces later as a
``discovered`` item from a walk turn.

Args: [wt_worklist_path] [service] [repo_root]
Outputs JSON: {"done_count","pending_count","added"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path


def emit(**kw: object) -> None:
    payload: dict[str, object] = {"done_count": 0, "pending_count": 0, "added": 0}
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _search_flows(repo_root: str) -> list[dict]:
    try:
        p = subprocess.run(
            ["ostler", "search", "", "--type", "flow", "--json"],
            cwd=repo_root, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(p.stdout or "[]")
        return data if isinstance(data, list) else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def main(logger: logging.Logger) -> None:
    wl_path = Path(sys.argv[1])
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    repo_root = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "."
    scope = f"docs/features/{service}/"

    data = json.loads(wl_path.read_text()) if wl_path.exists() else {"items": []}
    items = data.get("items", [])
    by_key = {(i.get("kind"), i.get("target")): i for i in items}

    added = 0
    for flow in _search_flows(repo_root):
        path = flow.get("path", "")
        if scope not in path:
            continue
        slug = Path(path).stem
        key = ("journey", f"flow:{slug}")
        existing = by_key.get(key)
        if existing:
            # A completed journey belongs to an earlier walkthrough invocation. Reopen it
            # so every fresh run captures current evidence; leave pending/active work alone
            # so interrupted runs still resume where they stopped.
            if existing.get("status") == "done":
                existing["status"] = "pending"
                existing["context"] = flow.get("title", slug)
                added += 1
            continue
        items.append({
            "kind": "journey", "target": f"flow:{slug}",
            "context": flow.get("title", slug), "status": "pending",
        })
        by_key[key] = items[-1]
        added += 1

    data["items"] = items
    wl_path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    if not pend:
        # Nothing to walk: the book documents no flow under this service's scope, so the
        # walk turns will find an empty drain and the run captures no evidence at all.
        logger.warning("no journeys seeded — no flow docs found under %s; "
                       "the walk has nothing to do", scope)
    logger.info("seeded walk worklist %s: %d journey(s) added, %d done / %d pending",
                wl_path, added, done, pend)
    emit(done_count=done, pending_count=pend, added=added)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("seed-walkthrough"))
