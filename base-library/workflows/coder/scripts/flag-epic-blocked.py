#!/usr/bin/env python3
"""Set a blocked epic aside for the rest of THIS run (coder, epic mode).

``select_story`` reports ``story_outcome="blocked"`` when an epic still has unbuilt
stories but none of them is runnable: they were given up on this run, they wait on a
dependency nothing will satisfy, or they were never authored. That is *not* a finished
epic, so it must not take the ``prune_epic`` → PR → merge path — the epic's remaining
scope would be merged as if it had been built.

The alternative to setting it aside is halting the run, and that is the wrong trade for
an unattended queue: one stuck epic would stop every independent epic behind it. So this
records the epic in a per-run blocked set (``<run_dir>/blocked-epics.txt``, one name per
line) and the workflow returns to ``select_epic``, which skips the names in that file.

Three properties make this safe:
  * **It terminates.** Each pass sets aside exactly one epic and the queue is finite, so
    the loop ends at the latest when every epic is blocked (``has_epic="no"`` → done).
  * **Nothing is lost.** The epic keeps its place in ``docs/epics/index.md`` and whatever
    work it accumulated stays committed on its own branch, unmerged. A later run — with a
    fresh, empty skip set — picks it up from the front of the queue again.
  * **It is per-run, like the story skip set it mirrors.** The file lives in the run dir,
    so an operator resets it by clearing the file or starting a new run.

Args: <epic> [<run_dir>] [<reason>]
Outputs JSON: {"epic_blocked": "yes"|"no", "blocked_epics": "<comma-separated>",
               "reason": "..."}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BLOCKED_FILE = "blocked-epics.txt"


def record_blocked(run_dir_arg: str, epic: str) -> list[str]:
    """Append ``epic`` to the per-run blocked set and return the whole set, in order.

    No run dir (story mode, or a hand-run node) means no per-run state to keep, so the
    epic is simply reported — the caller still routes away from ``prune_epic``, which is
    the part that must not happen.
    """
    if not run_dir_arg or not epic:
        return [epic] if epic else []
    run_dir = Path(run_dir_arg)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / BLOCKED_FILE
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing = [ln.strip() for ln in existing if ln.strip()]
    if epic not in existing:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{epic}\n")
        existing.append(epic)
    return existing


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    run_dir_arg = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    detail = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else ""

    if not epic:
        logger.warning("flag-epic-blocked called with no epic — nothing to set aside")
        print(json.dumps({"epic_blocked": "no", "blocked_epics": "",
                          "reason": "no epic supplied"}))
        return

    blocked = record_blocked(run_dir_arg, epic)
    reason = (f"epic '{epic}' set aside for this run"
              + (f": {detail}" if detail else "")
              + " — NOT merged; its branch keeps whatever it built")
    # Warning, not info: an unattended run that ends with epics set aside looks exactly
    # like one that finished the queue unless this is visible in the log.
    logger.warning("%s", reason)
    print(json.dumps({"epic_blocked": "yes", "blocked_epics": ",".join(blocked),
                      "reason": reason}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("flag-epic-blocked"))
