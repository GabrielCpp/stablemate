#!/usr/bin/env python3
"""Select the next inventory unit that still needs assessing (the per-unit loop driver).

Walks the frozen inventory in order and returns the first unit whose ``status`` is
``pending``. When none is left, ``has_unit`` is ``"no"`` and the workflow proceeds to
the coverage gate — the empty pending set **is** the coverage proof (structural, not
a post-hoc check).

Also derives the unit's finding-record path (``<findings_dir>/<slug>.md``) so the
assess/validate/mark nodes all agree on one location without re-deriving it.

Selection runs through the shared ``workhorse.worklist`` primitive: the inventory is a
worklist whose ``units`` are its items and whose done-states are ``assessed``/``clean``
(surveyor's own :class:`Scheme`), so ``select_next`` returns the first not-done unit — the
first ``pending`` — exactly as before, and its ``snapshot`` gives the dashboard progress
("12/40") and the kinds composition ("30 file · 10 folder") the run had no way to show.

Args:
    argv[1]  inventory    : repo-relative path to inventory.json
    argv[2]  findings_dir : repo-relative findings root

Outputs JSON: {"has_unit": "yes"|"no", "unit_id": "...", "unit_path": "...",
               "unit_kind": "...", "record_path": "...", "reason": "...",
               "progress": "...", "kinds": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

from workhorse import worklist as wl

# Surveyor's status vocabulary: a unit is *done* once it has a finding record (assessed)
# or was found clean; blocked units are set aside; everything else (pending) is selectable.
SURVEY_SCHEME = wl.Scheme(
    done=frozenset({"assessed", "clean"}), blocked=frozenset({"blocked"})
)


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def record_slug(unit_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


def emit(**kwargs: str) -> None:
    payload = {"has_unit": "no", "unit_id": "", "unit_path": "", "unit_kind": "",
               "record_path": "", "reason": "", "progress": "", "kinds": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    inv_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/inventory.json"
    findings_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/findings"

    root = find_repo_root()
    inv_path = root / inv_rel
    if not inv_path.is_file():
        logger.warning("no inventory at %s — expand_inventory must materialize it first", inv_rel)
        emit(reason=f"no inventory at {inv_rel} — expand_inventory must materialize it first")

    # The inventory is a worklist keyed under "units" (with `version`/`rules` siblings the
    # backend preserves). Load once, then let the shared primitive sequence and count it.
    backend = wl.JsonBackend(inv_path, items_key="units")
    try:
        units = backend.load()
    except (json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s is not parseable", inv_rel)
        emit(reason=f"inventory at {inv_rel} is not parseable — verify_records will flag it")

    snap = wl.snapshot(units, scheme=SURVEY_SCHEME)  # progress + kinds for the dashboard
    pick = wl.select_next(units, scheme=SURVEY_SCHEME)  # first not-done/not-blocked = first pending
    unit_id = str(pick.get("id", "")) if isinstance(pick, dict) else ""
    if not unit_id:
        # None left (or a degenerate pending unit with no id — nothing assessable): the
        # empty pending set is the coverage proof, so hand off to the coverage gate.
        logger.info("no pending units left — every unit has a finding record (or is blocked)")
        emit(reason="no pending units left — every unit has a finding record (or is blocked)",
             progress=snap["progress"], kinds=snap["kinds"])

    logger.info("selected pending unit '%s'", unit_id)
    emit(
        has_unit="yes",
        unit_id=unit_id,
        unit_path=str(pick.get("path", unit_id)),
        unit_kind=str(pick.get("kind", "")),
        record_path=f"{findings_rel}/{record_slug(unit_id)}.md",
        reason="first inventory unit still pending",
        progress=snap["progress"],
        kinds=snap["kinds"],
    )


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-next-unit"))
