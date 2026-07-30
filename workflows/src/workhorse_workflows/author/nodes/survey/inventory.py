"""Materializing the frozen unit list from enumeration rules, and correcting it locally.

The planner (or the operator) decides the *rule*; `expand_inventory` materializes the
*list*. An agent never emits the inventory itself — an agent listing hundreds of paths
reintroduces sampled enumeration one stage earlier, and glob/command expansion makes the
list complete **by construction**. The exhaustiveness claim of the whole survey rests on
that file, so it is durable, committed, and **frozen once built**: a resumed run that
produced a *different* list would silently break the coverage claim.

`split_unit` is the one sanctioned correction, and it is deliberately local: a folder unit
too big to assess in one bounded context is *replaced* by its immediate children and the
rest of the frozen list is untouched, so the coverage claim survives the correction.

Ported from `base-library/workflows/author/surveyor/scripts/{expand-inventory,split-unit}.py`.
`import yaml` is at the top of the file with no `ImportError` fallback: the workflow
declares what it imports and workhorse imports it before node one, so a "PyYAML is
unavailable, therefore — no findings" verdict is a shape this package cannot express.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

import yaml
from workhorse_workflows.author.nodes.survey._blueprint import blueprint
from workhorse_workflows.author.nodes.survey import _stubs
from workhorse_workflows.author.paths import survey_repo_root
from workhorse_workflows.author.schemas.survey import Expansion, SplitResult

#: What one enumeration rule may enumerate.
RULE_KINDS = {"folder", "file", "command"}
#: The inventory's status vocabulary. `pending` is the only selectable one.
UNIT_STATUSES = {"pending", "assessed", "clean", "blocked"}


def record_slug(unit_id: str) -> str:
    """Filename-safe slug a unit's finding record is stored under (findings/<slug>.md)."""
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


def _validate_rules(data: object) -> tuple[list[dict], list[str], list[str]]:
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
                errors.append(
                    f"rules[{i}] (command) missing non-empty `unit_kind` "
                    f"(what one emitted line IS, e.g. 'endpoint')"
                )
        elif not str(rule.get("glob") or "").strip():
            errors.append(f"rules[{i}] ({kind}) missing non-empty `glob`")
    excludes = data.get("exclude") or []
    if not isinstance(excludes, list):
        errors.append("`exclude` must be a list of fnmatch patterns")
        excludes = []
    return rules, [str(x) for x in excludes], errors


def _expand(
    root: Path, rules: list[dict], excludes: list[str]
) -> tuple[list[dict], list[str]]:
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
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"rules[{i}] command failed to run: {exc}")
                continue
            if proc.returncode != 0:
                errors.append(
                    f"rules[{i}] command exited {proc.returncode}: "
                    f"{(proc.stderr or '').strip()[:400]}"
                )
                continue
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if not lines:
                errors.append(
                    f"rules[{i}] command emitted no units — an empty enumeration "
                    f"is a rules problem, not a clean survey"
                )
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
            errors.append(
                f"rules[{i}] glob '{pattern}' matched no {kind}s — fix the rule "
                f"(a rule that enumerates nothing cannot claim coverage)"
            )

    # Record filenames are derived from unit ids; two ids sharing a slug would silently
    # share one record file and break per-unit coverage — reject at materialization time.
    by_slug: dict[str, str] = {}
    for u in units:
        slug = record_slug(u["id"])
        if slug in by_slug:
            errors.append(
                f"units '{by_slug[slug]}' and '{u['id']}' collide on record slug "
                f"'{slug}' — adjust the rules so unit ids stay distinguishable"
            )
        else:
            by_slug[slug] = u["id"]

    return units, errors


@blueprint.node(stub=_stubs.expanded)
def expand_inventory(
    logger: logging.Logger,
    rules: str = "docs/survey/units.yml",
    inventory: str = "docs/survey/inventory.json",
) -> Expansion:
    """Materialize the unit inventory from the enumeration rules — then freeze it.

    An existing inventory is consumed verbatim and never re-expanded. Units that later
    vanish without a finding record are a detectable drop (`verify_records`), not silent
    shrinkage.
    """
    rules_rel = rules.strip() or "docs/survey/units.yml"
    inv_rel = inventory.strip() or "docs/survey/inventory.json"

    root = survey_repo_root()
    inv_path = root / inv_rel

    # ── Freeze: an existing inventory is consumed verbatim, never re-expanded ──────────
    if inv_path.is_file():
        try:
            data = json.loads(inv_path.read_text(encoding="utf-8"))
            inv_units = data.get("units")
            if not isinstance(inv_units, list):
                raise ValueError("`units` is not a list")
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "existing inventory %s is not parseable JSON with a `units` list", inv_rel
            )
            return Expansion(
                expand_errors=(
                    f"existing inventory {inv_rel} is not parseable JSON with a `units` "
                    f"list — fix or remove it (it is the frozen coverage baseline)"
                )
            )
        pending = sum(
            1 for u in inv_units if isinstance(u, dict) and u.get("status") == "pending"
        )
        logger.info(
            "inventory already frozen at %s: %d unit(s), %d still pending — consumed as-is",
            inv_rel,
            len(inv_units),
            pending,
        )
        return Expansion(
            expand_ok=True,
            unit_count=len(inv_units),
            inventory_note=(
                f"inventory frozen at {inv_rel}: {len(inv_units)} unit(s), "
                f"{pending} still pending — consumed as-is, never re-planned"
            ),
        )

    rules_path = root / rules_rel
    if not rules_path.is_file():
        logger.warning("no rules file at %s — the planner must write it first", rules_rel)
        return Expansion(
            expand_errors=f"no rules file at {rules_rel} — the planner must write it first"
        )
    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("rules file %s is not valid YAML: %s", rules_rel, exc)
        return Expansion(expand_errors=f"rules file is not valid YAML: {exc}")

    parsed_rules, excludes, errors = _validate_rules(data)
    if errors:
        logger.warning(
            "rules file %s failed structural validation: %d error(s)", rules_rel, len(errors)
        )
        return Expansion(expand_errors="\n".join(errors))

    units, errors = _expand(root, parsed_rules, excludes)
    if errors:
        logger.warning("rules expansion produced %d error(s)", len(errors))
        return Expansion(expand_errors="\n".join(errors))
    if not units:
        logger.warning("rules expanded to zero units")
        return Expansion(
            expand_errors="rules expanded to zero units — the enumeration cannot be empty"
        )

    inv_path.parent.mkdir(parents=True, exist_ok=True)
    inv_path.write_text(
        json.dumps({"version": 1, "rules": rules_rel, "units": units}, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "materialized %d unit(s) into %s from %s — the list is now frozen",
        len(units),
        inv_rel,
        rules_rel,
    )
    return Expansion(
        expand_ok=True,
        unit_count=len(units),
        inventory_note=(
            f"materialized {len(units)} unit(s) into {inv_rel} from {rules_rel} — "
            f"the list is now frozen"
        ),
    )


def _load_excludes(root: Path, rules_rel: str) -> list[str]:
    """The rules file's `exclude` patterns, so split children honor the same fence."""
    if not rules_rel:
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


@blueprint.node(stub=_stubs.split)
def split_unit(logger: logging.Logger, inventory: str, unit_id: str) -> SplitResult:
    """Replace a too-big folder unit with its immediate children.

    Only `folder` units can split — a file or command unit has no children, so the
    assessor must assess it or mark it blocked. The split lineage stays detectable
    because every child path extends the parent's, which is how `verify_records` tells a
    split from a silent drop.
    """
    inv_rel = inventory.strip()
    unit_id = unit_id.strip()
    if not inv_rel or not unit_id:
        logger.warning("inventory and unit_id are both required")
        return SplitResult(split_errors="inventory and unit_id are both required")

    root = survey_repo_root()
    inv_path = root / inv_rel
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        return SplitResult(split_errors=f"inventory at {inv_rel} could not be read")

    units = data.get("units") or []
    idx = next(
        (
            i
            for i, u in enumerate(units)
            if isinstance(u, dict) and u.get("id") == unit_id
        ),
        None,
    )
    if idx is None:
        logger.warning("unit '%s' not found in %s", unit_id, inv_rel)
        return SplitResult(split_errors=f"unit '{unit_id}' not found in {inv_rel}")

    unit = units[idx]
    if unit.get("kind") != "folder":
        logger.warning(
            "unit '%s' is kind '%s' — only folder units can split", unit_id, unit.get("kind")
        )
        return SplitResult(
            split_errors=(
                f"unit '{unit_id}' is kind '{unit.get('kind')}' — only folder "
                f"units can split; assess it or mark it blocked"
            )
        )

    folder = root / str(unit.get("path") or unit_id)
    if not folder.is_dir():
        logger.warning("unit path '%s' is not a directory on disk", unit.get("path"))
        return SplitResult(
            split_errors=f"unit path '{unit.get('path')}' is not a directory on disk"
        )

    excludes = _load_excludes(root, str(data.get("rules") or ""))
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
        children.append(
            {
                "id": rel,
                "path": rel,
                "kind": "folder" if child.is_dir() else "file",
                "status": "pending",
            }
        )

    if not children:
        logger.warning("'%s' has no splittable children", unit_id)
        return SplitResult(
            split_errors=(
                f"'{unit_id}' has no splittable children — assess it as one "
                f"unit or mark it blocked"
            )
        )

    units[idx : idx + 1] = children
    inv_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info("split unit '%s' into %d children", unit_id, len(children))
    return SplitResult(split_ok=True, children_count=len(children))


__all__ = ["RULE_KINDS", "UNIT_STATUSES", "expand_inventory", "record_slug", "split_unit"]
