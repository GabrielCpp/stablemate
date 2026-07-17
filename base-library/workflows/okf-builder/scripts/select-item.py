#!/usr/bin/env python3
"""okf-builder: pop the next pending worklist item and mark it active.

Prefers an already-``active`` item (a crash mid-investigation is re-picked, not
skipped), else the first ``pending``. Empty → the drain is dry and the loop hands
off to the checkpoint (audit + coverage re-scan).

Args: [worklist_path] [max_items]
  max_items  hard cap on total investigations (done items); 0 = unlimited. When the cap
             is reached, over_budget=yes so the loop converges what it has instead of
             spending unbounded quota overnight.
Outputs JSON: {"has_item","over_budget","current_item","item_kind","item_target",
               "item_context","pending_count","done_count"}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "has_item": "no", "over_budget": "no", "current_item": "", "item_kind": "",
        "item_target": "", "item_context": "", "pending_count": 0, "done_count": 0,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    wl_path = Path(sys.argv[1])
    try:
        max_items = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else 0
    except ValueError:
        max_items = 0
    data = json.loads(wl_path.read_text())
    items = data.get("items", [])
    done = sum(1 for i in items if i.get("status") == "done")

    if max_items and done >= max_items:
        # Over budget: stop handing out work so the run converges the partial book
        # rather than burning quota all night. Pending items remain for a later resume.
        pend = sum(1 for i in items if i.get("status") == "pending")
        emit(has_item="no", over_budget="yes", pending_count=pend, done_count=done)

    active = [i for i in items if i.get("status") == "active"]
    pending = [i for i in items if i.get("status") == "pending"]
    pick = active[0] if active else (pending[0] if pending else None)
    if pick is None:
        emit(has_item="no", pending_count=0, done_count=done)

    pick["status"] = "active"
    wl_path.write_text(json.dumps(data, indent=2))
    pend = sum(1 for i in items if i.get("status") == "pending")
    emit(has_item="yes", current_item=json.dumps(pick), item_kind=pick.get("kind", ""),
         item_target=pick.get("target", ""), item_context=pick.get("context", ""),
         pending_count=pend, done_count=done)


if __name__ == "__main__":
    main()
