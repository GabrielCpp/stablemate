"""The parity survey's two ends: freezing the unit list, and emitting from it."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ostler import markdown
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


def parity_slug(value: str) -> str:
    """The record filename for a unit id."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


@blueprint.node
def load_parity_config(
    logger: logging.Logger,
    baseline: str,
    survey_dir: str = "docs/survey/legacy-vs-new",
    repo_dir: str = "",
) -> ParityConfig:
    """Resolve and validate the two documentation inventories being compared."""
    baseline = baseline.strip()
    survey_dir = survey_dir.strip() or "docs/survey/legacy-vs-new"

    root = launch_repo_root(repo_dir)
    target = paths.features_dir(root)
    backlog = paths.backlog_file(root)
    epics = paths.epics_dir(root)
    if not baseline or not (root / baseline).is_file():
        logger.warning("baseline inventory not found: %s", baseline or "(empty)")
        raise WorkflowFailed(
            f"baseline inventory not found: {baseline or '(empty)'}",
            failure_class="parity-baseline-missing",
            artifacts={"baseline": str(root / baseline)} if baseline else {},
        )
    if not (root / target).is_dir():
        logger.warning("target feature book not found: %s", target)
        raise WorkflowFailed(
            f"target feature book not found: {target}",
            failure_class="parity-target-missing",
            artifacts={"target": str(root / target)},
        )

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
    """Freeze one survey unit per baseline surface."""
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
    """Replace the parity-surveyor fence, or append one."""
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
    unit_manifest: str,
    repo_dir: str = "",
) -> EmitResult:
    """One backlog bullet per assessed surface that no new-app feature already owns."""
    root = launch_repo_root(repo_dir)
    backlog = paths.backlog_file(root)
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
        record = markdown.split(record_path.read_text(encoding="utf-8")).frontmatter or {}
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
    "PARITY_HEADING",
    "emit_parity_backlog",
    "expand_parity_inventory",
    "load_parity_config",
    "parity_slug",
    "replace_parity_section",
]
