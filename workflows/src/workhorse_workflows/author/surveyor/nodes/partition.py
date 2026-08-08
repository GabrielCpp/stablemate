"""The partition gate, and the artifacts the survey hands to author.

Clustering the finding records into epic/story candidates is the one place in the whole
surveyor where real synthesis judgment is allowed — so it is also the one place that needs
a mechanical backstop. `validate_partition` is that backstop: clustering may be smart, but
it may never be LOSSY. An assessed unit in no cluster would drop silently out of the
generated backlog, which is exactly the tail-dropping the surveyor exists to prevent.

`emit_artifacts` then writes the survey's whole output as author's *existing* input, so
author runs unchanged in epic mode. The exhaustiveness claim is proved upstream, here, by
the chain `verify_records` → `validate_partition` → `emit_artifacts`; author does not
re-assert it at intake, because a gate there would be searching a haystack containing the
very backlog this node wrote.

Ported from `surveyor/scripts/{validate-partition,emit-artifacts}.py`.
"""
from __future__ import annotations

import json
import logging
import re

import yaml
from workhorse_workflows.author.shared.survey.blueprint import blueprint
from workhorse_workflows.author.shared.survey import stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.survey import EmitResult, PartitionCheck

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
#: `mechanical` is one checklist story over many units; `dedicated` is one gnarly unit
#: getting its own story. Nothing stack-shaped, and deliberately only two.
STRATEGIES = {"mechanical", "dedicated"}

SECTION_BEGIN = "<!-- surveyor:begin — generated; do not edit inside this fence -->"
SECTION_END = "<!-- surveyor:end -->"
SECTION_HEADING = "## Survey findings"


@blueprint.node(stub=stubs.partitioned)
def validate_partition(
    logger: logging.Logger,
    partition: str = "docs/survey/partition.yaml",
    inventory: str = "docs/survey/inventory.json",
    repo_dir: str = "",
) -> PartitionCheck:
    """Every non-clean unit maps into at least one cluster, and no cluster invents units.

    Structural checks first (unique kebab ids, a title, a known strategy, a non-empty
    `units` list, every listed unit in the frozen inventory and `assessed`), then the real
    gate: the orphan sweep. `clean` and operator-accepted `blocked` units carry no
    remediation work, so they may not appear at all.
    """
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
                f"(it becomes the backlog bullet's [id])"
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

    # The real gate: no assessed unit may fall out of the partition.
    orphans = sorted(
        uid
        for uid, st in unit_status.items()
        if st == "assessed" and uid not in clustered_units
    )
    for uid in orphans:
        errors.append(
            f"assessed unit '{uid}' appears in NO cluster — its findings would "
            f"silently drop out of the generated backlog; add it to a cluster"
        )

    if errors:
        logger.warning("partition validation failed with %d error(s)", len(errors))
        return PartitionCheck(partition_errors="\n".join(errors))
    logger.info("partition valid: %d cluster(s) cover every assessed unit", len(clusters))
    return PartitionCheck(partition_ok=True)


def bullet_for(cluster: dict) -> str:
    """One backlog bullet. The cluster id in it is the traceability hop author's
    `sourceBullet` chain extends downward: unit → finding → backlog bullet → seed → story.
    """
    cid = str(cluster["id"])
    title = str(cluster.get("title", "")).strip()
    strategy = str(cluster.get("strategy", ""))
    pattern = str(cluster.get("remediation_pattern", ""))
    n = len(cluster.get("units") or [])
    hints = [f"pattern: {pattern}"]
    hints.append(
        f"{n} unit(s), {strategy}"
        + (
            " checklist — keep as ONE story with a per-unit checklist"
            if strategy == "mechanical"
            else ""
        )
    )
    notes = str(cluster.get("notes") or "").strip().replace("\n", " ")
    if notes:
        hints.append(notes)
    return f"- [survey-{cid}] {title} ({'; '.join(hints)})"


def replace_section(text: str, section: str) -> str:
    """Replace the marker-fenced survey section, or append one if absent.

    Wholesale replacement inside the fence is what makes re-emitting idempotent; anything
    outside it — a human-curated backlog, coder's `## Filed by coder` section — is
    untouched.
    """
    begin, end = text.find(SECTION_BEGIN), text.find(SECTION_END)
    if begin != -1 and end != -1 and end > begin:
        return text[:begin] + section + text[end + len(SECTION_END) :]
    body = text.rstrip("\n")
    prefix = (body + "\n\n") if body else "# Backlog\n\n"
    return prefix + SECTION_HEADING + "\n\n" + section + "\n"


@blueprint.node(stub=stubs.emitted)
def emit_artifacts(
    logger: logging.Logger,
    partition: str = "docs/survey/partition.yaml",
    inventory: str = "docs/survey/inventory.json",
    backlog: str = "",
    unit_manifest: str = "docs/survey/unit-manifest.json",
    repo_dir: str = "",
) -> EmitResult:
    """Write the generated backlog bullets and the unit-level manifest.

    The generated backlog is the author handoff. The unit manifest remains survey
    traceability: every unit carries the bullet ids that cover it, but author does not read
    or mutate it while writing stories.

    Runs after `validate_partition` passed, so the partition is trusted here.
    """
    part_rel = partition.strip() or "docs/survey/partition.yaml"
    inv_rel = inventory.strip() or "docs/survey/inventory.json"
    manifest_rel = unit_manifest.strip() or "docs/survey/unit-manifest.json"

    root = survey_repo_root(repo_dir)
    backlog_rel = paths.backlog_file(root, backlog)
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

    # ── Backlog bullets: one per cluster, in the marker-fenced generated section ───────
    ordered = sorted(
        (c for c in clusters if isinstance(c, dict)),
        key=lambda c: (c.get("order", 10**6), str(c.get("id", ""))),
    )
    section = "\n".join([SECTION_BEGIN, *(bullet_for(c) for c in ordered), SECTION_END])

    backlog_path = root / backlog_rel
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    existing = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_path.write_text(replace_section(existing, section), encoding="utf-8")

    # ── Unit manifest: every unit + the bullets that cover it ──────────────────────────
    bullets_by_unit: dict[str, list[str]] = {}
    clusters_by_unit: dict[str, list[str]] = {}
    for c in ordered:
        cid = str(c.get("id", ""))
        for uid in c.get("units") or []:
            bullets_by_unit.setdefault(str(uid), []).append(f"survey-{cid}")
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
        f"wrote {len(ordered)} bullet(s) into {backlog_rel} and "
        f"{len(manifest_units)} unit(s) into {manifest_rel}"
    )
    logger.info(
        "wrote %d bullet(s) into %s and %d unit(s) into %s",
        len(ordered),
        backlog_rel,
        len(manifest_units),
        manifest_rel,
    )
    return EmitResult(emit_ok=True, bullet_count=len(ordered), emit_note=note)


__all__ = [
    "SECTION_BEGIN",
    "SECTION_END",
    "SECTION_HEADING",
    "STRATEGIES",
    "bullet_for",
    "emit_artifacts",
    "replace_section",
    "validate_partition",
]
