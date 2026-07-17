#!/usr/bin/env python3
"""Select the next inventory unit that still needs assessing (the per-unit loop driver).

Walks the frozen inventory in order and returns the first unit whose ``status`` is
``pending``. When none is left, ``has_unit`` is ``"no"`` and the workflow proceeds to
the coverage gate — the empty pending set **is** the coverage proof (structural, not
a post-hoc check).

Also derives the unit's finding-record path (``<findings_dir>/<slug>.md``) so the
assess/validate/mark nodes all agree on one location without re-deriving it.

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  inventory    : repo-relative path to inventory.json
    argv[2]  findings_dir : repo-relative findings root

Outputs JSON: {"has_unit": "yes"|"no", "unit_id": "...", "unit_path": "...",
               "unit_kind": "...", "record_path": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path


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
               "record_path": "", "reason": ""}
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
    try:
        units = json.loads(inv_path.read_text(encoding="utf-8")).get("units") or []
    except (json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s is not parseable", inv_rel)
        emit(reason=f"inventory at {inv_rel} is not parseable — verify_records will flag it")

    for u in units:
        if not isinstance(u, dict) or u.get("status") != "pending":
            continue
        unit_id = str(u.get("id", ""))
        if not unit_id:
            continue
        logger.info("selected pending unit '%s'", unit_id)
        emit(
            has_unit="yes",
            unit_id=unit_id,
            unit_path=str(u.get("path", unit_id)),
            unit_kind=str(u.get("kind", "")),
            record_path=f"{findings_rel}/{record_slug(unit_id)}.md",
            reason="first inventory unit still pending",
        )

    logger.info("no pending units left — every unit has a finding record (or is blocked)")
    emit(reason="no pending units left — every unit has a finding record (or is blocked)")


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-next-unit"))
