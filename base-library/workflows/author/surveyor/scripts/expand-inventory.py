#!/usr/bin/env python3
"""Deterministically materialize the unit inventory from enumeration rules — then freeze it.

The planner (or the operator) decides the *rule*; this script materializes the *list*.
An agent never emits the inventory itself — an agent listing hundreds of paths
reintroduces sampled enumeration one stage earlier; glob/command expansion makes the
list complete **by construction**. The exhaustiveness claim of the whole survey rests
on this file, so it is:

- **durable and committed** (the survey's analog of ``docs/epics/index.md``), and
- **frozen once built**: if the inventory already exists this script consumes the
  existing list verbatim and never re-expands — a resumed run that produced a
  *different* list would silently break the coverage claim. Units that later vanish
  without a finding record are a detectable drop (``verify-records.py``), not silent
  shrinkage.

Rules file (YAML), planner-authored or operator-pinned::

    rules:
      - kind: folder                # one unit per matched DIRECTORY
        glob: "src/lib/components/*"
      - kind: file                  # one unit per matched FILE
        glob: "src/routes/**/*.svelte"
      - kind: command               # one unit per non-empty stdout line — for units
        command: "bin/list-endpoints" #   that are not files at all (endpoints, tables)
        unit_kind: endpoint
    exclude:                        # optional, fnmatch on repo-relative paths
      - "**/node_modules/**"

Mixed granularity is first-class: folder-per-unit here, file-per-unit there, in one
rules file. The workflow depends only on the inventory contract, never on how the
list was produced.

Stdlib + PyYAML (available in the local-worker runtime).

Args:
    argv[1]  rules     : repo-relative path to the enumeration-rules YAML
    argv[2]  inventory : repo-relative path to inventory.json (written, or consumed if frozen)

Outputs JSON: {"expand_ok": "yes"|"no", "expand_errors": "<lines>",
               "unit_count": <int>, "inventory_note": "<summary>"}
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

RULE_KINDS = {"folder", "file", "command"}
UNIT_STATUSES = {"pending", "assessed", "clean", "blocked"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: str, errors: list[str] | str = "", count: int = 0, note: str = "") -> None:
    msg = errors if isinstance(errors, str) else "\n".join(errors)
    print(json.dumps({
        "expand_ok": ok, "expand_errors": msg, "unit_count": count, "inventory_note": note,
    }))
    sys.exit(0)


def record_slug(unit_id: str) -> str:
    """Filename-safe slug a unit's finding record is stored under (findings/<slug>.md)."""
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


def validate_rules(data: object) -> tuple[list[dict], list[str], list[str]]:
    """Return (rules, excludes, errors). Structural validation only — no expansion."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [], [], ["rules file root must be a mapping with a `rules:` list"]
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        return [], [], ["`rules` must be a non-empty list of enumeration rules"]
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"rules[{i}] is not a mapping")
            continue
        kind = rule.get("kind")
        if kind not in RULE_KINDS:
            errors.append(f"rules[{i}] kind '{kind}' not one of {sorted(RULE_KINDS)}")
        elif kind == "command":
            if not str(rule.get("command") or "").strip():
                errors.append(f"rules[{i}] (command) missing non-empty `command`")
            if not str(rule.get("unit_kind") or "").strip():
                errors.append(f"rules[{i}] (command) missing non-empty `unit_kind` "
                              f"(what one emitted line IS, e.g. 'endpoint')")
        elif not str(rule.get("glob") or "").strip():
            errors.append(f"rules[{i}] ({kind}) missing non-empty `glob`")
    excludes = data.get("exclude") or []
    if not isinstance(excludes, list):
        errors.append("`exclude` must be a list of fnmatch patterns")
        excludes = []
    return rules, [str(x) for x in excludes], errors


def expand(root: Path, rules: list[dict], excludes: list[str]) -> tuple[list[dict], list[str]]:
    """Expand validated rules into unit entries. Returns (units, errors)."""
    units: list[dict] = []
    seen_ids: set[str] = set()
    errors: list[str] = []

    def excluded(rel: str) -> bool:
        return any(fnmatch(rel, pat) for pat in excludes)

    def add(unit_id: str, kind: str) -> None:
        if unit_id in seen_ids:
            return  # same unit matched by two rules — one entry
        seen_ids.add(unit_id)
        units.append({"id": unit_id, "path": unit_id, "kind": kind, "status": "pending"})

    for i, rule in enumerate(rules):
        kind = rule["kind"]
        if kind == "command":
            cmd = str(rule["command"]).strip()
            try:
                proc = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True,
                                      text=True, timeout=300)
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"rules[{i}] command failed to run: {exc}")
                continue
            if proc.returncode != 0:
                errors.append(f"rules[{i}] command exited {proc.returncode}: "
                              f"{(proc.stderr or '').strip()[:400]}")
                continue
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if not lines:
                errors.append(f"rules[{i}] command emitted no units — an empty enumeration "
                              f"is a rules problem, not a clean survey")
                continue
            for line in lines:
                add(line, str(rule["unit_kind"]).strip())
            continue

        pattern = str(rule["glob"]).strip().strip("/")
        matched = 0
        for p in sorted(root.glob(pattern)):
            rel = p.relative_to(root).as_posix()
            if excluded(rel):
                continue
            if kind == "folder" and p.is_dir():
                add(rel, "folder")
                matched += 1
            elif kind == "file" and p.is_file():
                add(rel, "file")
                matched += 1
        if matched == 0:
            errors.append(f"rules[{i}] glob '{pattern}' matched no {kind}s — fix the rule "
                          f"(a rule that enumerates nothing cannot claim coverage)")

    # Record filenames are derived from unit ids; two ids sharing a slug would silently
    # share one record file and break per-unit coverage — reject at materialization time.
    by_slug: dict[str, str] = {}
    for u in units:
        slug = record_slug(u["id"])
        if slug in by_slug:
            errors.append(f"units '{by_slug[slug]}' and '{u['id']}' collide on record slug "
                          f"'{slug}' — adjust the rules so unit ids stay distinguishable")
        else:
            by_slug[slug] = u["id"]

    return units, errors


def main(logger: logging.Logger) -> None:
    rules_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/units.yml"
    inv_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/inventory.json"

    root = find_repo_root()
    inv_path = root / inv_rel

    # ── Freeze: an existing inventory is consumed verbatim, never re-expanded ──────────
    if inv_path.is_file():
        try:
            data = json.loads(inv_path.read_text(encoding="utf-8"))
            inv_units = data.get("units")
            assert isinstance(inv_units, list)
        except (json.JSONDecodeError, ValueError, AssertionError):
            logger.warning("existing inventory %s is not parseable JSON with a `units` list", inv_rel)
            emit("no", [f"existing inventory {inv_rel} is not parseable JSON with a `units` "
                        f"list — fix or remove it (it is the frozen coverage baseline)"])
            return
        pending = sum(1 for u in inv_units if isinstance(u, dict) and u.get("status") == "pending")
        logger.info("inventory already frozen at %s: %d unit(s), %d still pending — consumed as-is",
                    inv_rel, len(inv_units), pending)
        emit("yes", count=len(inv_units),
             note=f"inventory frozen at {inv_rel}: {len(inv_units)} unit(s), "
                  f"{pending} still pending — consumed as-is, never re-planned")
        return

    if yaml is None:
        logger.warning("PyYAML is unavailable — cannot parse the rules file")
        emit("no", ["PyYAML is required to parse the rules file but is unavailable"])
        return
    rules_path = root / rules_rel
    if not rules_path.is_file():
        logger.warning("no rules file at %s — the planner must write it first", rules_rel)
        emit("no", [f"no rules file at {rules_rel} — the planner must write it first"])
        return
    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("rules file %s is not valid YAML: %s", rules_rel, exc)
        emit("no", [f"rules file is not valid YAML: {exc}"])
        return

    rules, excludes, errors = validate_rules(data)
    if errors:
        logger.warning("rules file %s failed structural validation: %d error(s)", rules_rel, len(errors))
        emit("no", errors)
        return

    units, errors = expand(root, rules, excludes)
    if errors:
        logger.warning("rules expansion produced %d error(s)", len(errors))
        emit("no", errors)
        return
    if not units:
        logger.warning("rules expanded to zero units")
        emit("no", ["rules expanded to zero units — the enumeration cannot be empty"])
        return

    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text(json.dumps({
        "version": 1,
        "rules": rules_rel,
        "units": units,
    }, indent=2) + "\n", encoding="utf-8")
    logger.info("materialized %d unit(s) into %s from %s — the list is now frozen",
                len(units), inv_rel, rules_rel)
    emit("yes", count=len(units),
         note=f"materialized {len(units)} unit(s) into {inv_rel} from {rules_rel} — "
              f"the list is now frozen")


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("expand-inventory"))
