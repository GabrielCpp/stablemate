#!/usr/bin/env python3
"""Self-healing granularity: replace a too-big folder unit with its children.

When the assessor concludes one bounded context cannot faithfully assess a unit
(``status: split``), the fix is LOCAL — the inventory grows by that unit's immediate
children and the loop continues. There is no global re-planning: the rest of the
frozen list is untouched, so the coverage claim survives the correction. The parent
entry is REPLACED by its children (the split lineage stays detectable: every child
path extends the parent path, which is how ``verify-records.py`` distinguishes a
split from a silent drop).

Only ``folder`` units can split (a file or command unit has no children — the
assessor must assess it or mark it ``blocked``). Children are the folder's immediate
entries, minus dotfiles and anything the rules file's ``exclude`` patterns reject.

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  inventory : repo-relative path to inventory.json
    argv[2]  unit_id   : the folder unit to split

Outputs JSON: {"split_ok": "yes"|"no", "children_count": <int>, "split_errors": "<lines>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from fnmatch import fnmatch
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: str, count: int = 0, errors: list[str] | str = "") -> None:
    msg = errors if isinstance(errors, str) else "\n".join(errors)
    print(json.dumps({"split_ok": ok, "children_count": count, "split_errors": msg}))
    sys.exit(0)


def load_excludes(root: Path, rules_rel: str) -> list[str]:
    """The rules file's `exclude` patterns, so split children honor the same fence."""
    if not rules_rel or yaml is None:
        return []
    rules_path = root / rules_rel
    if not rules_path.is_file():
        return []
    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    excludes = data.get("exclude") if isinstance(data, dict) else None
    return [str(x) for x in excludes] if isinstance(excludes, list) else []


def main(logger: logging.Logger) -> None:
    inv_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    unit_id = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    if not inv_rel or not unit_id:
        logger.warning("inventory and unit_id are both required")
        emit("no", errors=["inventory and unit_id are both required"])

    root = find_repo_root()
    inv_path = root / inv_rel
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        emit("no", errors=[f"inventory at {inv_rel} could not be read"])

    units = data.get("units") or []
    idx = next((i for i, u in enumerate(units)
                if isinstance(u, dict) and u.get("id") == unit_id), None)
    if idx is None:
        logger.warning("unit '%s' not found in %s", unit_id, inv_rel)
        emit("no", errors=[f"unit '{unit_id}' not found in {inv_rel}"])

    unit = units[idx]
    if unit.get("kind") != "folder":
        logger.warning("unit '%s' is kind '%s' — only folder units can split", unit_id, unit.get("kind"))
        emit("no", errors=[f"unit '{unit_id}' is kind '{unit.get('kind')}' — only folder "
                           f"units can split; assess it or mark it blocked"])

    folder = root / str(unit.get("path") or unit_id)
    if not folder.is_dir():
        logger.warning("unit path '%s' is not a directory on disk", unit.get("path"))
        emit("no", errors=[f"unit path '{unit.get('path')}' is not a directory on disk"])

    excludes = load_excludes(root, str(data.get("rules") or ""))
    existing_ids = {u.get("id") for u in units if isinstance(u, dict)}
    children: list[dict] = []
    for child in sorted(folder.iterdir()):
        if child.name.startswith("."):
            continue
        rel = child.relative_to(root).as_posix()
        if any(fnmatch(rel, pat) for pat in excludes):
            continue
        if rel in existing_ids:
            continue  # already its own unit (e.g. matched by another rule)
        children.append({"id": rel, "path": rel,
                         "kind": "folder" if child.is_dir() else "file",
                         "status": "pending"})

    if not children:
        logger.warning("'%s' has no splittable children", unit_id)
        emit("no", errors=[f"'{unit_id}' has no splittable children — assess it as one "
                           f"unit or mark it blocked"])

    units[idx:idx + 1] = children
    inv_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info("split unit '%s' into %d children", unit_id, len(children))
    emit("yes", count=len(children))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("split-unit"))
