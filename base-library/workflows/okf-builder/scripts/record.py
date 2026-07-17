#!/usr/bin/env python3
"""okf-builder: mark the current item done and merge newly-discovered items.

The universal worklist mutator — used after enumerate (seed surfaces), investigate
(seed an item's spawned children), checkpoint (seed fixups), and recheck (seed
coverage/journey items). Dedupes by (kind, target) against ALL items. A coverage recheck may set
``requeue: true`` to reopen an already-done below-bar item.

Args: [worklist_path] [current_item_json_or_empty] [discovered_json_or_empty]
Outputs JSON: {"done_count","pending_count","added"}
"""
from __future__ import annotations

import ast
import json
import logging
import sys
from pathlib import Path


def _loads(s: str) -> object:
    """Parse a JSON blob, tolerating a Python-repr fallback (single-quoted) in case a
    caller rendered a list with bare ``{{ }}`` instead of ``| tojson``."""
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        try:
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return None


def emit(**kw: object) -> None:
    payload: dict[str, object] = {"done_count": 0, "pending_count": 0, "added": 0}
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _norm(s: object) -> str:
    return " ".join(str(s or "").split()).strip().lower()


def main(logger: logging.Logger) -> None:
    wl_path = Path(sys.argv[1])
    current = sys.argv[2] if len(sys.argv) > 2 else ""
    discovered = sys.argv[3] if len(sys.argv) > 3 else ""
    data = json.loads(wl_path.read_text())
    items = data.get("items", [])
    by_key = {(_norm(i.get("kind")), _norm(i.get("target"))): i for i in items}

    if current:
        cur = _loads(current)
        if isinstance(cur, dict):
            ck = (_norm(cur.get("kind")), _norm(cur.get("target")))
            logger.info("marking item '%s' (%s) done", cur.get("target", "?"),
                        cur.get("kind", "?"))
            for i in items:
                if (_norm(i.get("kind")), _norm(i.get("target"))) == ck:
                    i["status"] = "done"
        else:
            # Unparseable current item: nothing is marked done, so the loop re-picks the
            # same active item next round and appears to spin in place.
            logger.warning("current item is not parseable JSON — no item marked done: %.200s",
                           current)

    added = 0
    if discovered:
        dlist = _loads(discovered)
        if not isinstance(dlist, list):
            # The agent's discoveries are dropped silently otherwise — the crawl just
            # stops finding new work and looks like it ran out of surface.
            logger.warning("discovered items are not a JSON list — dropping them: %.200s",
                           discovered)
            dlist = []
        for d in dlist:
            if not isinstance(d, dict):
                continue
            k = (_norm(d.get("kind")), _norm(d.get("target")))
            if not d.get("kind") or not d.get("target"):
                continue
            existing = by_key.get(k)
            if existing:
                if d.get("requeue") is True and existing.get("status") == "done":
                    existing["status"] = "pending"
                    existing["context"] = d.get("context", existing.get("context", ""))
                    added += 1
                continue
            items.append({"kind": d["kind"], "target": d["target"],
                          "context": d.get("context", ""), "status": "pending"})
            by_key[k] = items[-1]
            added += 1

    data["items"] = items
    wl_path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    logger.info("worklist %s: added %d new item(s), now %d done / %d pending",
                wl_path, added, done, pend)
    emit(done_count=done, pending_count=pend, added=added)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("record"))
