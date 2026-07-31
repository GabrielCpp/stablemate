"""The parity survey's two ends: freezing the unit list, and emitting from it.

A parity survey asks one question of a rewrite — which legacy surfaces have no home in the
new app — and it is a *survey*, so it gets the same exhaustiveness guarantee: one frozen
unit per baseline surface, one finding record each, and the empty pending set as the proof.
The middle of the loop is shared verbatim with the surveyor (`select_next_unit`,
`validate_record`, `mark_unit`, `verify_records`); only these three nodes differ.

The differences are worth naming, because they are what make it a parity survey rather than
a second copy of one:

* the frozen list is not enumerated from rules — it is *transcribed* from a baseline
  inventory that already exists, so there is no granularity planner and no split;
* there is no partition step. Each missing surface is its own gap, so clustering would
  merge exactly the things a parity backlog needs kept apart;
* emission suppresses any surface a record claims is already owned by a new-app feature.
  That is the one judgment the assessor makes, and it is recorded per unit (in
  `existing_owner`) so the suppression is auditable rather than invisible.

These nodes resolve the repo through `launch_repo_root(repo_dir)` — the run's input, else
cwd, no walk —
because that is what their scripts did. See `author/shared/paths.py`.

Ported from `surveyor/scripts/{load-parity-config,expand-parity-inventory,
emit-parity-backlog}.py`.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.shared.survey.blueprint import blueprint
from workhorse_workflows.author.shared.survey import stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import launch_repo_root
from workhorse_workflows.author.shared.schemas.parity import ParityConfig
from workhorse_workflows.author.shared.schemas.survey import EmitResult, Expansion

PARITY_BEGIN = "<!-- parity-surveyor:begin — generated; do not edit inside this fence -->"
PARITY_END = "<!-- parity-surveyor:end -->"
PARITY_HEADING = "## Legacy surfaces missing from the new app"
#: The emitter's own front-matter reader. Looser than `records.FRONT_MATTER_RE` — it does
#: not require the closing fence to end a line — and kept as its own pattern because it
#: runs after `verify_records` already accepted every record it reads.
PARITY_FRONT_MATTER = re.compile(r"^\s*---\s*\n(.*?)\n---", re.S)


def parity_slug(value: str) -> str:
    """The record filename for a unit id. Same rule as `record_slug`, its own copy in the
    script, kept separate so the two emitters can diverge without a shared edit."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


@blueprint.node
def load_parity_config(
    logger: logging.Logger,
    baseline: str,
    target: str = "",
    survey_dir: str = "docs/survey/legacy-vs-new",
    backlog: str = "",
    epics: str = "",
    repo_dir: str = "",
) -> ParityConfig:
    """Resolve and validate the two documentation inventories being compared.

    Both must exist before anything else runs: a parity survey with no baseline has nothing
    to be exhaustive *about*, and one with no target feature book would report every legacy
    surface as missing.
    """
    baseline = baseline.strip()
    survey_dir = survey_dir.strip() or "docs/survey/legacy-vs-new"

    root = launch_repo_root(repo_dir)
    target = paths.features_dir(root, target)
    backlog = paths.backlog_file(root, backlog)
    epics = paths.epics_dir(root, epics)
    if not baseline or not (root / baseline).is_file():
        logger.warning("baseline inventory not found: %s", baseline or "(empty)")
        raise WorkflowFailed(f"baseline inventory not found: {baseline or '(empty)'}")
    if not (root / target).is_dir():
        logger.warning("target feature book not found: %s", target)
        raise WorkflowFailed(f"target feature book not found: {target}")

    logger.info(
        "config loaded: baseline=%s target=%s survey_dir=%s", baseline, target, survey_dir
    )
    return ParityConfig(
        repo_root=str(root),
        baseline_inventory=baseline,
        target_features=target,
        survey_dir=survey_dir,
        inventory=f"{survey_dir}/inventory.json",
        findings_dir=f"{survey_dir}/findings",
        unit_manifest=f"{survey_dir}/unit-manifest.json",
        backlog=backlog,
        epics_dir=epics,
    )


@blueprint.node(stub=stubs.expanded)
def expand_parity_inventory(
    logger: logging.Logger, baseline: str, inventory: str, repo_dir: str = ""
) -> Expansion:
    """Freeze one survey unit per baseline surface.

    Same freeze semantics as `expand_inventory`: an inventory already on disk is the
    coverage baseline and is consumed verbatim, never re-derived. Surfaces the baseline
    marks `rewriteSurface: true` are out of scope by construction — the rewrite already
    owns them.
    """
    root = launch_repo_root(repo_dir)
    output = root / inventory
    if output.is_file():
        try:
            units = json.loads(output.read_text(encoding="utf-8"))["units"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("frozen inventory %s is invalid: %s", inventory, exc)
            return Expansion(expand_errors=f"frozen inventory is invalid: {exc}")
        logger.info(
            "inventory already frozen at %s: %d unit(s) — consumed as-is",
            inventory,
            len(units),
        )
        return Expansion(
            expand_ok=True,
            unit_count=len(units),
            inventory_note=f"inventory frozen at {inventory}",
        )

    try:
        data = json.loads((root / baseline).read_text(encoding="utf-8"))
        entries = data["entries"]
        if not isinstance(entries, list):
            raise TypeError("entries is not a list")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("baseline inventory %s is invalid: %s", baseline, exc)
        return Expansion(expand_errors=f"baseline inventory is invalid: {exc}")

    base_dir = Path(baseline).parent
    units = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("rewriteSurface") is True:
            continue
        area, slug = str(entry.get("area", "")).strip(), str(entry.get("slug", "")).strip()
        if not area or not slug:
            logger.warning("baseline entry missing area/slug")
            return Expansion(
                expand_errors="every baseline entry must have non-empty area and slug"
            )
        unit_id = f"legacy/{area}/{slug}"
        if unit_id in seen:
            logger.warning("duplicate baseline surface: %s", unit_id)
            return Expansion(expand_errors=f"duplicate baseline surface: {unit_id}")
        seen.add(unit_id)
        units.append(
            {
                "id": unit_id,
                "path": (base_dir / area / f"{slug}.md").as_posix(),
                "kind": "legacy-surface",
                "status": "pending",
                "area": area,
                "slug": slug,
                "title": str(entry.get("title", slug)),
                "route": str(entry.get("route", "")),
            }
        )

    if not units:
        logger.warning("baseline inventory %s contains no non-rewrite surfaces", baseline)
        return Expansion(
            expand_errors="baseline inventory contains no non-rewrite surfaces"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"version": 1, "baseline": baseline, "units": units}, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("froze %d baseline surfaces into %s", len(units), inventory)
    return Expansion(
        expand_ok=True,
        unit_count=len(units),
        inventory_note=f"froze {len(units)} baseline surfaces",
    )


def replace_parity_section(text: str, section: str) -> str:
    """Replace the parity-surveyor fence, or append one. Its own copy of the rule, with its
    own markers, so a repo can carry both surveys' generated sections side by side."""
    begin, end = text.find(PARITY_BEGIN), text.find(PARITY_END)
    if begin != -1 and end > begin:
        return text[:begin] + section + text[end + len(PARITY_END) :]
    prefix = text.rstrip() + "\n\n" if text.strip() else "# Backlog\n\n"
    return f"{prefix}{PARITY_HEADING}\n\n{section}\n"


@blueprint.node(stub=stubs.emitted)
def emit_parity_backlog(
    logger: logging.Logger,
    inventory: str,
    findings_dir: str,
    backlog: str,
    unit_manifest: str,
    repo_dir: str = "",
) -> EmitResult:
    """One backlog bullet per assessed surface that no new-app feature already owns.

    The manifest carries *every* unit, including the suppressed ones and the owner that
    suppressed them, so "we decided this one is already covered" stays an auditable claim
    rather than an absence.
    """
    root = launch_repo_root(repo_dir)
    try:
        data = json.loads((root / inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("inventory at %s could not be read: %s", inventory, exc)
        return EmitResult(emit_errors=str(exc))

    bullets: list[str] = []
    manifest_units: list[dict[str, object]] = []
    suppressed = 0
    for unit in data.get("units", []):
        uid = str(unit.get("id", ""))
        record_path = root / findings_dir / f"{parity_slug(uid)}.md"
        match = PARITY_FRONT_MATTER.match(record_path.read_text(encoding="utf-8"))
        record = yaml.safe_load(match.group(1)) if match else {}
        status = str(record.get("status", ""))
        owner = str(record.get("existing_owner", "")).strip()
        bullet_id = f"legacy-parity-{unit.get('area')}-{unit.get('slug')}"
        emitted = status == "assessed" and not owner
        if emitted:
            finding = (record.get("findings") or [{}])[0]
            description = " ".join(str(finding.get("description", "")).split())
            bullets.append(f"- [{bullet_id}] {description}")
        elif status == "assessed" and owner:
            suppressed += 1
        manifest_units.append(
            {
                "id": uid,
                "path": unit.get("path", ""),
                "status": status,
                "existingOwner": owner,
                "bullet": bullet_id if emitted else "",
            }
        )

    section = "\n".join([PARITY_BEGIN, *bullets, PARITY_END])
    backlog_path = root / backlog
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    existing = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_path.write_text(replace_parity_section(existing, section), encoding="utf-8")

    manifest_path = root / unit_manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "generatedBy": "parity-surveyor",
                "baseline": data.get("baseline", ""),
                "units": manifest_units,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    note = (
        f"wrote {len(bullets)} missing-surface bullet(s); suppressed {suppressed} "
        f"already-owned surface(s)"
    )
    logger.info(
        "wrote %d missing-surface bullet(s); suppressed %d already-owned surface(s)",
        len(bullets),
        suppressed,
    )
    return EmitResult(emit_ok=True, bullet_count=len(bullets), emit_note=note)


__all__ = [
    "PARITY_BEGIN",
    "PARITY_END",
    "PARITY_FRONT_MATTER",
    "PARITY_HEADING",
    "emit_parity_backlog",
    "expand_parity_inventory",
    "load_parity_config",
    "parity_slug",
    "replace_parity_section",
]
