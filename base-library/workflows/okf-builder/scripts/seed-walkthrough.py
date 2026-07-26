#!/usr/bin/env python3
"""okf-builder walkthrough: seed the walk worklist with the *unconfirmed* delta.

The walk's product is visual evidence: a screenshot per screen state and, via ``ostler vet``,
a registered crop per documented component. So the walk's delta is not the code delta — a screen
is behind because it carries no evidence, not because its source moved. Design §10.3 calls this
the **unconfirmed** set and computes it by set arithmetic against the book, needing no git anchor.

Two item kinds are seeded, and the order matters:

* ``journey`` — one per ``flow`` doc that still traverses an unconfirmed screen. Journeys go first
  because they arrive with state the earlier steps established, which is the only way some screens
  render at all.
* ``screen`` — one per unconfirmed screen, as the sweep that catches what no journey covers. The
  walk turn resolves its path with ``ostler reach`` rather than navigating to ``route:``, so a
  screen is reached the way a user would or is reported as a book defect.

Re-seeding is therefore idempotent against evidence: a screen that already carries a ``vet:``
bullet is not re-walked, and a journey whose screens are all confirmed stays ``done``. The
previous behaviour — reopening *every* done journey on every run — made each run redo the same
paths regardless of what was already registered, so the gap never closed.

Args: [wt_worklist_path] [service] [repo_root]
Outputs JSON: {"done_count","pending_count","added","unconfirmed_count","screen_count"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# The bullet that proves a screen was visually registered against a running app. Its absence is
# what makes a screen unconfirmed — `screenshot:` alone is a picture, not a registration.
#
# It is counted **anywhere on the screen**, not only on the screen's file node. A vet report
# describes one *state*, and a state is produced by an interaction, so walks attach the bullet to
# the `mount-load-*` interaction that renders it. Looking only at the file node scores every such
# screen unconfirmed and re-walks work that is already done.
VET_BULLET = "vet"


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "done_count": 0, "pending_count": 0, "added": 0,
        "unconfirmed_count": 0, "screen_count": 0,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _screen_of(node_id: str, by_id: dict) -> str | None:
    """The screen a node lives on: its file-level node, when that file is a screen doc."""
    file_id = node_id.split("#", 1)[0]
    node = by_id.get(file_id)
    return file_id if node is not None and node.get("type") == "screen" else None


def _book(repo_root: str, service: str, logger: logging.Logger) -> dict | None:
    """The service's graph, in-process. A graph that will not load seeds nothing, loudly."""
    try:
        from ostler import Ostler, graph as graph_mod
    except ImportError as exc:
        logger.warning("ostler is not importable — the walk cannot be seeded: %s", exc)
        return None
    try:
        return graph_mod.build(Ostler(repo_root).graph, surface=service or None)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        logger.warning("could not load the OKF graph — the walk cannot be seeded: %s", exc)
        return None


def main(logger: logging.Logger) -> None:
    wl_path = Path(sys.argv[1])
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    repo_root = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "."

    data = json.loads(wl_path.read_text()) if wl_path.exists() else {"items": []}
    items = data.get("items", [])
    by_key = {(i.get("kind"), i.get("target")): i for i in items}

    book = _book(repo_root, service, logger)
    if book is None:
        emit(done_count=sum(1 for i in items if i.get("status") == "done"),
             pending_count=sum(1 for i in items if i.get("status") == "pending"))

    by_id = {n["id"]: n for n in book["nodes"]}
    screens = [n for n in book["nodes"] if n["type"] == "screen" and n["kind"] == "file"]
    registered = {
        screen for n in book["nodes"] if VET_BULLET in n.get("bullets", {})
        if (screen := _screen_of(n["id"], by_id)) is not None
    }
    unconfirmed = {n["id"] for n in screens} - registered

    added = 0

    def _seed(kind: str, target: str, context: str) -> None:
        nonlocal added
        existing = by_key.get((kind, target))
        if existing is None:
            items.append({"kind": kind, "target": target, "context": context,
                          "status": "pending"})
            by_key[(kind, target)] = items[-1]
            added += 1
        elif existing.get("status") == "done":
            # Done, but the evidence it should have produced is absent — the earlier run did not
            # finish the job, so reopen it. A confirmed target never reaches this branch.
            existing["status"] = "pending"
            existing["context"] = context
            added += 1

    for flow in (n for n in book["nodes"] if n["type"] == "flow"):
        touched = {s for s in (_screen_of(e["to"], by_id) for e in flow["edges"]) if s}
        if not touched & unconfirmed:
            continue  # every screen this journey covers is already registered
        _seed("journey", f"flow:{Path(flow['path']).stem}", flow["title"])

    for screen in sorted(unconfirmed):
        _seed("screen", screen, by_id[screen]["title"])

    data["items"] = items
    wl_path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    if not pend:
        logger.info("nothing to walk: all %d screen(s) under %s carry `%s:` evidence",
                    len(screens), service or "(whole book)", VET_BULLET)
    logger.info("seeded walk worklist %s: %d item(s) added, %d/%d screen(s) unconfirmed, "
                "%d done / %d pending", wl_path, added, len(unconfirmed), len(screens),
                done, pend)
    emit(done_count=done, pending_count=pend, added=added,
         unconfirmed_count=len(unconfirmed), screen_count=len(screens))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("seed-walkthrough"))
