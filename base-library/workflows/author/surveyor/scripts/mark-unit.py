#!/usr/bin/env python3
"""Flip the inventory entry's status from its (validated) finding record — the loop's
durable "mark done".

The happy path runs after ``validate-record.py`` passed: read the record's ``status``
(``assessed`` / ``clean`` / ``blocked``) and stamp it onto the unit's inventory entry so
``select-next-unit.py`` never re-selects it. Fully resumable: the inventory + record
files ARE the loop state.

The degraded path is the give-up escape: when the record is missing or still invalid
after the bounded fix loop, the unit must not wedge the whole survey — it is marked
``blocked`` (with a stub record carrying the reason in ``openGaps`` if none exists) and
the loop moves on. ``verify-records.py`` re-surfaces every blocked unit at the coverage
gate, so nothing marked here is silently dropped — a blocked unit is an OPEN gap until
an operator re-pends it or records an accepted disposition.

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  inventory   : repo-relative path to inventory.json
    argv[2]  unit_id     : the unit to mark
    argv[3]  record_path : repo-relative path to the unit's finding record
    argv[4]  fallback    : optional reason used when the record is missing/unreadable
                           (the give-up paths pass their errors here)

Outputs JSON: {"marked": "yes"|"no", "unit_status": "<status>", "mark_note": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
RECORD_STATUSES = {"assessed", "clean", "blocked"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def record_status(path: Path) -> str | None:
    """The record's front-matter `status`, or None when missing/unparseable/invalid."""
    if not path.is_file() or yaml is None:
        return None
    m = _FRONT_MATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    status = data.get("status") if isinstance(data, dict) else None
    return status if status in RECORD_STATUSES else None


def write_stub(path: Path, unit_id: str, reason: str) -> None:
    """A minimal blocked record so the gap stays durable even when the assessor's own
    record never materialized (or could not be repaired)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "type: survey-finding\n"
        f"unit: {unit_id}\n"
        "status: blocked\n"
        "openGaps:\n"
        f"  - {json.dumps(reason)}\n"
        "---\n\n"
        f"# Survey finding: {unit_id}\n\n"
        "Stub written by mark-unit.py — the assessment did not produce a valid record.\n",
        encoding="utf-8",
    )


def main(logger: logging.Logger) -> None:
    inv_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    unit_id = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    record_rel = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else ""
    fallback = sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else ""

    def emit(marked: str, status: str = "", note: str = "") -> None:
        print(json.dumps({"marked": marked, "unit_status": status, "mark_note": note}))

    if not inv_rel or not unit_id or not record_rel:
        logger.warning("inventory, unit_id, and record_path are all required")
        emit("no", note="inventory, unit_id, and record_path are all required")
        return

    root = find_repo_root()
    record_path = root / record_rel
    status = record_status(record_path)
    note = "unit marked from its record's status"
    if status is None:
        # Give-up path: never wedge the loop — durably record the gap and move on.
        status = "blocked"
        reason = fallback or "assessment produced no valid finding record"
        if not record_path.is_file():
            write_stub(record_path, unit_id, reason)
            note = "no record on disk — wrote a blocked stub carrying the reason"
            logger.warning("unit '%s': no record on disk — wrote a blocked stub (%s)", unit_id, reason)
        else:
            note = "record exists but is invalid — unit marked blocked; verify_records will re-surface it"
            logger.warning("unit '%s': record exists but is invalid — marked blocked", unit_id)

    inv_path = root / inv_rel
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        emit("no", status, f"inventory at {inv_rel} could not be read")
        return

    for u in data.get("units") or []:
        if isinstance(u, dict) and u.get("id") == unit_id:
            u["status"] = status
            inv_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            logger.info("unit '%s' marked '%s'", unit_id, status)
            emit("yes", status, note)
            return

    logger.warning("unit '%s' not found in %s", unit_id, inv_rel)
    emit("no", status, f"unit '{unit_id}' not found in {inv_rel}")


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("mark-unit"))
