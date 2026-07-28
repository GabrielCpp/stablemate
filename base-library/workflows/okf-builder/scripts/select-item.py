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
               "item_context","pending_count","done_count","done_this_run",
               "progress","kinds"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse import worklist as wl


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "has_item": "no", "over_budget": "no", "current_item": "", "item_kind": "",
        "item_target": "", "item_context": "", "pending_count": 0, "done_count": 0,
        "done_this_run": 0, "progress": "", "kinds": "",
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
    # One worklist snapshot drives both the budget math (counts.done for the per-run cap)
    # and the dashboard (progress "3/12" + the kinds line "5 surface · 3 layer" — okf's
    # items are multi-kind, so that composition is the natural activity subtitle). The
    # items already carry `kind`/`status`, so they are handed to the stateless functions
    # as-is (no Backend; this script owns the JSON read/write and the budget cap the
    # primitive knows nothing about). See workhorse.worklist.
    snap = wl.snapshot(items)
    done = snap["counts"]["done"]
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
        # Reads as a silent early exit from the outside: the loop just stops handing
        # out work with pending items left, which looks identical to a dry drain.
        logger.warning(
            "over budget — %d done this run reaches the cap of %d; handing out no more "
            "work with %d still pending (resume to continue)",
            this_run, max_items, snap["counts"]["pending"],
        )
        emit(has_item="no", over_budget="yes", pending_count=snap["counts"]["pending"],
             done_count=done, done_this_run=this_run, progress=snap["progress"],
             kinds=snap["kinds"])

    pick = wl.select_next(items)  # active-first crash-safe re-pick, then first pending
    if pick is None:
        logger.info("drain is dry — no active or pending items; handing off to checkpoint")
        emit(has_item="no", pending_count=0, done_count=done, done_this_run=this_run,
             progress=snap["progress"], kinds=snap["kinds"])

    resumed = pick.get("status") == "active"
    pick["status"] = "active"
    wl_path.write_text(json.dumps(data, indent=2))
    pend = wl.counts(items)["pending"]  # one fewer after the flip
    logger.info(
        "picked %s item '%s' (%s), %d still pending",
        "resumed active" if resumed else "next pending",
        pick.get("target", "?"), pick.get("kind", "?"), pend,
    )
    emit(has_item="yes", current_item=json.dumps(pick), item_kind=pick.get("kind", ""),
         item_target=pick.get("target", ""), item_context=pick.get("context", ""),
         pending_count=pend, done_count=done, done_this_run=this_run,
         progress=snap["progress"], kinds=snap["kinds"])


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-item"))
