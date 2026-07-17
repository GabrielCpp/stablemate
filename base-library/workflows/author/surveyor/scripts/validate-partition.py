#!/usr/bin/env python3
"""Deterministic partition gate: every non-clean unit maps into at least one cluster.

The partitioner (an agent) clusters the finding records into epic/story candidates —
the one place the design allows real synthesis judgment. This gate is the mechanical
backstop on that judgment: clustering may be smart, but it may never be LOSSY. A unit
that was assessed with findings and appears in no cluster would fall out of the
generated backlog silently — the exact tail-dropping failure the surveyor exists to
prevent.

Partition file shape (YAML, written by the partitioner)::

    clusters:
      - id: icon-button-missing-accessible-name   # kebab, unique
        title: "Give every icon-only button an accessible name"
        remediation_pattern: icon-button-missing-accessible-name
        strategy: mechanical            # one checklist story over many units
        units: [src/lib/Button, ...]    # inventory ids this cluster remediates
        notes: "ordering/grouping hints for the author"   # optional
      - id: datepicker-keyboard-model
        strategy: dedicated             # one gnarly unit, its own story
        ...

Checks: the file parses; cluster ids are unique kebab slugs; every cluster has a
title, a valid strategy, and a non-empty ``units`` list; every listed unit exists in
the inventory; and — the real gate — every inventory unit whose record status is
``assessed`` appears in ≥ 1 cluster. ``clean`` units and (operator-accepted)
``blocked`` units carry no remediation work, so they may not appear at all.

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  partition    : repo-relative path to partition.yaml
    argv[2]  inventory    : repo-relative path to inventory.json

Outputs JSON: {"partition_ok": "yes"|"no", "partition_errors": "<lines>"}
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

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STRATEGIES = {"mechanical", "dedicated"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: bool, errors: list[str]) -> None:
    print(json.dumps({"partition_ok": "yes" if ok else "no",
                      "partition_errors": "\n".join(errors)}))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    part_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/partition.yaml"
    inv_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/inventory.json"

    root = find_repo_root()
    if yaml is None:
        logger.warning("PyYAML is unavailable — cannot parse the partition file")
        emit(False, ["PyYAML is required to parse the partition file but is unavailable"])

    part_path = root / part_rel
    if not part_path.is_file():
        logger.warning("no partition file at %s — the partitioner must write it", part_rel)
        emit(False, [f"no partition file at {part_rel} — the partitioner must write it"])
    try:
        part = yaml.safe_load(part_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("partition file %s is not valid YAML: %s", part_rel, exc)
        emit(False, [f"partition file is not valid YAML: {exc}"])

    try:
        units = json.loads((root / inv_rel).read_text(encoding="utf-8")).get("units") or []
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        emit(False, [f"inventory at {inv_rel} could not be read"])

    unit_status = {str(u.get("id")): u.get("status") for u in units if isinstance(u, dict)}

    errors: list[str] = []
    clusters = part.get("clusters") if isinstance(part, dict) else None
    if not isinstance(clusters, list) or not clusters:
        emit(False, ["partition file must carry a non-empty `clusters:` list"])

    clustered_units: set[str] = set()
    seen_ids: set[str] = set()
    for i, c in enumerate(clusters):
        if not isinstance(c, dict):
            errors.append(f"clusters[{i}] is not a mapping")
            continue
        cid = str(c.get("id") or "")
        if not _SLUG_RE.match(cid):
            errors.append(f"clusters[{i}] id '{cid or '?'}' must be a kebab-case slug "
                          f"(it becomes the backlog bullet's [id])")
        elif cid in seen_ids:
            errors.append(f"clusters[{i}] duplicate id '{cid}'")
        else:
            seen_ids.add(cid)
        if not str(c.get("title") or "").strip():
            errors.append(f"clusters[{i}] ({cid or '?'}) missing non-empty `title`")
        if c.get("strategy") not in STRATEGIES:
            errors.append(f"clusters[{i}] ({cid or '?'}) strategy '{c.get('strategy')}' not "
                          f"one of {sorted(STRATEGIES)}")
        if not _SLUG_RE.match(str(c.get("remediation_pattern") or "")):
            errors.append(f"clusters[{i}] ({cid or '?'}) `remediation_pattern` must be a "
                          f"kebab-case slug")
        c_units = c.get("units")
        if not isinstance(c_units, list) or not c_units:
            errors.append(f"clusters[{i}] ({cid or '?'}) must list at least one unit")
            continue
        for uid in c_units:
            uid = str(uid)
            if uid not in unit_status:
                errors.append(f"clusters[{i}] ({cid or '?'}) names unit '{uid}' which is not "
                              f"in the inventory — clusters partition the FROZEN list, they "
                              f"never invent units")
            elif unit_status[uid] != "assessed":
                errors.append(f"clusters[{i}] ({cid or '?'}) names unit '{uid}' whose status "
                              f"is '{unit_status[uid]}' — only `assessed` units carry work")
            else:
                clustered_units.add(uid)

    # The real gate: no assessed unit may fall out of the partition.
    orphans = sorted(uid for uid, st in unit_status.items()
                     if st == "assessed" and uid not in clustered_units)
    for uid in orphans:
        errors.append(f"assessed unit '{uid}' appears in NO cluster — its findings would "
                      f"silently drop out of the generated backlog; add it to a cluster")

    if errors:
        logger.warning("partition validation failed with %d error(s)", len(errors))
    else:
        logger.info("partition valid: %d cluster(s) cover every assessed unit", len(clusters))
    emit(not errors, errors)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-partition"))
