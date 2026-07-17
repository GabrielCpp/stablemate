#!/usr/bin/env python3
"""okf-builder: pop the next pending worklist item and mark it active.

Prefers an already-``active`` item (a crash mid-investigation is re-picked, not
skipped), else the first ``pending``. Empty → the drain is dry and the loop hands
off to the checkpoint (audit + coverage re-scan).

Args: [worklist_path] [max_items] [done_baseline]
  max_items      cap on investigations completed by THIS run; 0 = unlimited. When the cap is
                 reached, over_budget=yes so the loop converges what it has instead of
                 spending unbounded quota overnight.
  done_baseline  the worklist's done count when this run started (from prepare.py). The cap
                 is measured against it, because counting `done` over the whole file makes
                 `max_items` a *lifetime* cap: a resumed worklist already at the ceiling is
                 instantly over budget and hands out zero items, and the run reports success
                 having done nothing.
Outputs JSON: {"has_item","over_budget","current_item","item_kind","item_target",
               "item_context","pending_count","done_count","done_this_run"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "has_item": "no", "over_budget": "no", "current_item": "", "item_kind": "",
        "item_target": "", "item_context": "", "pending_count": 0, "done_count": 0,
        "done_this_run": 0,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    wl_path = Path(sys.argv[1])
    try:
        max_items = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else 0
    except ValueError:
        max_items = 0
    try:
        baseline = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
    except ValueError:
        baseline = 0
    data = json.loads(wl_path.read_text())
    items = data.get("items", [])
    done = sum(1 for i in items if i.get("status") == "done")
    # Clamp: a baseline above the count means the worklist shrank under the run (a reset
    # mid-flight). Trusting it would make `done_this_run` negative and the cap unreachable.
    this_run = max(0, done - min(baseline, done))
    logger.info(
        "worklist %s: %d items, %d done (%d this run, baseline %d), cap %s",
        wl_path, len(items), done, this_run, baseline, max_items or "none",
    )

    if max_items and this_run >= max_items:
        # Over budget: stop handing out work so the run converges the partial book
        # rather than burning quota all night. Pending items remain for a later resume.
        pend = sum(1 for i in items if i.get("status") == "pending")
        # Reads as a silent early exit from the outside: the loop just stops handing
        # out work with pending items left, which looks identical to a dry drain.
        logger.warning(
            "over budget — %d done this run reaches the cap of %d; handing out no more "
            "work with %d still pending (resume to continue)", this_run, max_items, pend,
        )
        emit(has_item="no", over_budget="yes", pending_count=pend, done_count=done,
             done_this_run=this_run)

    active = [i for i in items if i.get("status") == "active"]
    pending = [i for i in items if i.get("status") == "pending"]
    pick = active[0] if active else (pending[0] if pending else None)
    if pick is None:
        logger.info("drain is dry — no active or pending items; handing off to checkpoint")
        emit(has_item="no", pending_count=0, done_count=done, done_this_run=this_run)

    pick["status"] = "active"
    wl_path.write_text(json.dumps(data, indent=2))
    pend = sum(1 for i in items if i.get("status") == "pending")
    logger.info(
        "picked %s item '%s' (%s), %d still pending",
        "resumed active" if active else "next pending",
        pick.get("target", "?"), pick.get("kind", "?"), pend,
    )
    emit(has_item="yes", current_item=json.dumps(pick), item_kind=pick.get("kind", ""),
         item_target=pick.get("target", ""), item_context=pick.get("context", ""),
         pending_count=pend, done_count=done, done_this_run=this_run)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-item"))
