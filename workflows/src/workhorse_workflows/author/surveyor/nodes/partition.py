"""The partition gate, and the artifacts the survey hands to author."""
from __future__ import annotations

import json
import logging
import re
from pathlib import PurePosixPath

import yaml
from workhorse_workflows.author.shared.survey.blueprint import blueprint
from workhorse_workflows.author.shared.survey import stubs
from workhorse_workflows.author.shared.survey.filing import PATTERN, Proposal, file_proposals, segment
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.survey import EmitResult, PartitionCheck

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STRATEGIES = {"mechanical", "dedicated"}


@blueprint.node(stub=stubs.partitioned)
def validate_partition(
    logger: logging.Logger,
    partition: str = "docs/survey/partition.yaml",
    inventory: str = "docs/survey/inventory.json",
    repo_dir: str = "",
) -> PartitionCheck:
    """Every non-clean unit maps into at least one cluster, and no cluster invents units."""
    part_rel = partition.strip() or "docs/survey/partition.yaml"
    inv_rel = inventory.strip() or "docs/survey/inventory.json"
    root = survey_repo_root(repo_dir)

    part_path = root / part_rel
    if not part_path.is_file():
        logger.warning("no partition file at %s — the partitioner must write it", part_rel)
        return PartitionCheck(
            partition_errors=(
                f"no partition file at {part_rel} — the partitioner must write it"
            )
        )
    try:
        part = yaml.safe_load(part_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.warning("partition file %s is not valid YAML: %s", part_rel, exc)
        return PartitionCheck(partition_errors=f"partition file is not valid YAML: {exc}")

    try:
        units = json.loads((root / inv_rel).read_text(encoding="utf-8")).get("units") or []
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        return PartitionCheck(partition_errors=f"inventory at {inv_rel} could not be read")

    unit_status = {str(u.get("id")): u.get("status") for u in units if isinstance(u, dict)}

    errors: list[str] = []
    clusters = part.get("clusters") if isinstance(part, dict) else None
    if not isinstance(clusters, list) or not clusters:
        return PartitionCheck(
            partition_errors="partition file must carry a non-empty `clusters:` list"
        )

    clustered_units: set[str] = set()
    seen_ids: set[str] = set()
    for i, c in enumerate(clusters):
        if not isinstance(c, dict):
            errors.append(f"clusters[{i}] is not a mapping")
            continue
        cid = str(c.get("id") or "")
        if not _SLUG_RE.match(cid):
            errors.append(
                f"clusters[{i}] id '{cid or '?'}' must be a kebab-case slug "
                f"(it names the cluster in the survey artifacts)"
            )
        elif cid in seen_ids:
            errors.append(f"clusters[{i}] duplicate id '{cid}'")
        else:
            seen_ids.add(cid)
        if not str(c.get("title") or "").strip():
            errors.append(f"clusters[{i}] ({cid or '?'}) missing non-empty `title`")
        if c.get("strategy") not in STRATEGIES:
            errors.append(
                f"clusters[{i}] ({cid or '?'}) strategy '{c.get('strategy')}' not "
                f"one of {sorted(STRATEGIES)}"
            )
        if not _SLUG_RE.match(str(c.get("remediation_pattern") or "")):
            errors.append(
                f"clusters[{i}] ({cid or '?'}) `remediation_pattern` must be a "
                f"kebab-case slug"
            )
        c_units = c.get("units")
        if not isinstance(c_units, list) or not c_units:
            errors.append(f"clusters[{i}] ({cid or '?'}) must list at least one unit")
            continue
        for raw in c_units:
            uid = str(raw)
            if uid not in unit_status:
                errors.append(
                    f"clusters[{i}] ({cid or '?'}) names unit '{uid}' which is not "
                    f"in the inventory — clusters partition the FROZEN list, they "
                    f"never invent units"
                )
            elif unit_status[uid] != "assessed":
                errors.append(
                    f"clusters[{i}] ({cid or '?'}) names unit '{uid}' whose status "
                    f"is '{unit_status[uid]}' — only `assessed` units carry work"
                )
            else:
                clustered_units.add(uid)

    orphans = sorted(
        uid
        for uid, st in unit_status.items()
        if st == "assessed" and uid not in clustered_units
    )
    for uid in orphans:
        errors.append(
            f"assessed unit '{uid}' appears in NO cluster — its findings would "
            f"silently drop out of the filed records; add it to a cluster"
        )

    if errors:
        logger.warning("partition validation failed with %d error(s)", len(errors))
        return PartitionCheck(partition_errors="\n".join(errors))
    logger.info("partition valid: %d cluster(s) cover every assessed unit", len(clusters))
    return PartitionCheck(partition_ok=True)


def common_area(paths: list[str]) -> str:
    """The last directory segment shared by every path, or ``general`` when none is."""
    parents = [PurePosixPath(p.strip("/")).parent.parts for p in paths if p.strip("/")]
    if not parents:
        return "general"
    shared: list[str] = []
    for level in zip(*parents, strict=False):
        if len(set(level)) != 1:
            break
        shared.append(level[0])
    return segment(shared[-1]) if shared else "general"


def proposal_for(cluster: dict, paths: dict[str, str] | None = None) -> Proposal:
    """One cluster as the record it files."""
    cid = str(cluster["id"])
    strategy = str(cluster.get("strategy", ""))
    units = [str(u) for u in cluster.get("units") or []]
    lines = [
        f"Cluster `{cid}`, remediation pattern `{cluster.get('remediation_pattern', '')}`.",
        f"{len(units)} unit(s), {strategy}"
        + (
            " checklist: keep as ONE story with a per-unit checklist."
            if strategy == "mechanical"
            else "."
        ),
        "Units: " + ", ".join(f"`{u}`" for u in units),
    ]
    notes = " ".join(str(cluster.get("notes") or "").split())
    if notes:
        lines.append(notes)
    return Proposal(
        key=cid,
        area=common_area([(paths or {}).get(u, u) for u in units]),
        pattern=segment(str(cluster.get("remediation_pattern", "")), PATTERN),
        symbols=tuple(units),
        summary=" ".join(str(cluster.get("title", "")).split()),
        body="\n\n".join(lines),
    )


@blueprint.node(stub=stubs.emitted)
def emit_artifacts(
    logger: logging.Logger,
    partition: str = "docs/survey/partition.yaml",
    inventory: str = "docs/survey/inventory.json",
    unit_manifest: str = "docs/survey/unit-manifest.json",
    repo_dir: str = "",
) -> EmitResult:
    """File one record per cluster and write the unit-level manifest."""
    part_rel = partition.strip() or "docs/survey/partition.yaml"
    inv_rel = inventory.strip() or "docs/survey/inventory.json"
    manifest_rel = unit_manifest.strip() or "docs/survey/unit-manifest.json"

    root = survey_repo_root(repo_dir)
    try:
        part = yaml.safe_load((root / part_rel).read_text(encoding="utf-8"))
        clusters = part.get("clusters") or []
        if not isinstance(clusters, list) or not clusters:
            raise ValueError("no clusters")
    except (OSError, yaml.YAMLError, AttributeError, ValueError):
        logger.warning(
            "partition at %s could not be read — run the partition gate first", part_rel
        )
        return EmitResult(
            emit_errors=(
                f"partition at {part_rel} could not be read — run the partition gate first"
            )
        )
    try:
        units = json.loads((root / inv_rel).read_text(encoding="utf-8")).get("units") or []
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        return EmitResult(emit_errors=f"inventory at {inv_rel} could not be read")

    paths = {
        str(u.get("id", "")): str(u.get("path") or u.get("id", "")) for u in units if isinstance(u, dict)
    }
    ordered = sorted(
        (c for c in clusters if isinstance(c, dict)),
        key=lambda c: (c.get("order", 10**6), str(c.get("id", ""))),
    )
    filed = file_proposals(logger, root, repo_dir, "survey", [proposal_for(c, paths) for c in ordered])
    if filed.errors:
        return EmitResult(emit_errors=filed.errors)

    bullets_by_unit: dict[str, list[str]] = {}
    clusters_by_unit: dict[str, list[str]] = {}
    for c in ordered:
        cid = str(c.get("id", ""))
        for uid in c.get("units") or []:
            bullets_by_unit.setdefault(str(uid), []).append(filed.ids[cid])
            clusters_by_unit.setdefault(str(uid), []).append(cid)

    manifest_units = []
    for u in units:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("id", ""))
        manifest_units.append(
            {
                "id": uid,
                "path": str(u.get("path", uid)),
                "kind": str(u.get("kind", "")),
                "status": str(u.get("status", "")),
                "bullets": bullets_by_unit.get(uid, []),
                "clusters": clusters_by_unit.get(uid, []),
            }
        )

    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "generatedBy": "surveyor",
                "inventory": inv_rel,
                "units": manifest_units,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    note = (
        f"filed {filed.new} of {len(ordered)} cluster record(s) and "
        f"wrote {len(manifest_units)} unit(s) into {manifest_rel}"
    )
    logger.info(note)
    return EmitResult(emit_ok=True, bullet_count=len(ordered), emit_note=note)


__all__ = [
    "STRATEGIES",
    "emit_artifacts",
    "proposal_for",
    "validate_partition",
]
