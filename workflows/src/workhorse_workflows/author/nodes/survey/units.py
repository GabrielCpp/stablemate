"""Walking the frozen list: pick the next pending unit, and mark one done.

The inventory is a **worklist** — `workhorse.worklist` sequences it and counts it — whose
items are its `units` and whose done-states are `assessed`/`clean`. So the loop needs no
state of its own: the inventory file and the finding records *are* the loop state, which
is what makes the survey resumable at any point.

Both nodes are shared by the surveyor and the parity surveyor: same scheme, same file
shape, same per-unit record convention.

Ported from `base-library/workflows/author/surveyor/scripts/{select-next-unit,mark-unit}.py`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from workhorse import worklist as wl
from workhorse_workflows.author.nodes.survey._blueprint import blueprint
from workhorse_workflows.author.nodes.survey.inventory import record_slug
from workhorse_workflows.author.nodes.survey.records import FRONT_MATTER_RE, RECORD_STATUSES
from workhorse_workflows.author.paths import survey_repo_root
from workhorse_workflows.author.schemas.survey import MarkResult, UnitPick

#: Surveyor's status vocabulary: a unit is *done* once it has a finding record
#: (assessed) or was found clean; blocked units are set aside; everything else
#: (pending) is selectable.
SURVEY_SCHEME = wl.Scheme(
    done=frozenset({"assessed", "clean"}), blocked=frozenset({"blocked"})
)



@blueprint.node
def select_next_unit(
    logger: logging.Logger,
    inventory: str = "docs/survey/inventory.json",
    findings_dir: str = "docs/survey/findings",
) -> UnitPick:
    """The first unit still `pending`, or the news that none is left.

    When none is left, `has_unit` is false and the flow proceeds to the coverage gate —
    the empty pending set **is** the coverage proof, structural rather than a post-hoc
    check. Also derives the unit's finding-record path so the assess/validate/mark nodes
    all agree on one location without re-deriving it.
    """
    inv_rel = inventory.strip() or "docs/survey/inventory.json"
    findings_rel = findings_dir.strip() or "docs/survey/findings"

    root = survey_repo_root()
    inv_path = root / inv_rel
    if not inv_path.is_file():
        logger.warning(
            "no inventory at %s — expand_inventory must materialize it first", inv_rel
        )
        return UnitPick(
            reason=f"no inventory at {inv_rel} — expand_inventory must materialize it first"
        )

    backend = wl.JsonBackend(inv_path, items_key="units")
    try:
        units = backend.load()
    except (json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s is not parseable", inv_rel)
        return UnitPick(
            reason=f"inventory at {inv_rel} is not parseable — verify_records will flag it"
        )

    snap = wl.snapshot(units, scheme=SURVEY_SCHEME)  # progress + kinds for the dashboard
    pick = wl.select_next(units, scheme=SURVEY_SCHEME)  # first not-done/not-blocked
    unit_id = str(pick.get("id", "")) if isinstance(pick, dict) else ""
    if not unit_id:
        # None left (or a degenerate pending unit with no id — nothing assessable): the
        # empty pending set is the coverage proof, so hand off to the coverage gate.
        reason = "no pending units left — every unit has a finding record (or is blocked)"
        logger.info(reason)
        return UnitPick(reason=reason, progress=snap["progress"], kinds=snap["kinds"])

    logger.info("selected pending unit '%s'", unit_id)
    return UnitPick(
        has_unit=True,
        unit_id=unit_id,
        unit_path=str(pick.get("path", unit_id)),
        unit_kind=str(pick.get("kind", "")),
        record_path=f"{findings_rel}/{record_slug(unit_id)}.md",
        reason="first inventory unit still pending",
        progress=snap["progress"],
        kinds=snap["kinds"],
    )


def _record_status(path: Path) -> str | None:
    """The record's front-matter `status`, or None when missing/unparseable/invalid.

    Deliberately not `records.load_record`: this is mark-unit's own lenient reader, which
    treats *every* way of failing to state a valid status as one thing — no record. It
    runs on the give-up path, after validation already had its say.
    """
    if not path.is_file():
        return None
    m = FRONT_MATTER_RE.match(path.read_text(encoding="utf-8"))
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    status = data.get("status") if isinstance(data, dict) else None
    return status if status in RECORD_STATUSES else None


def _write_stub(path: Path, unit_id: str, reason: str) -> None:
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
        "Stub written by mark_unit — the assessment did not produce a valid record.\n",
        encoding="utf-8",
    )


@blueprint.node
def mark_unit(
    logger: logging.Logger,
    inventory: str,
    unit_id: str,
    record_path: str,
    fallback: str = "",
) -> MarkResult:
    """Stamp the unit's inventory entry with its (validated) record's status.

    The happy path runs after `validate_record` passed. The degraded path is the give-up
    escape: when the record is missing or still invalid after the bounded fix loop, the
    unit must not wedge the whole survey — it is marked `blocked`, with a stub record
    carrying the reason in `openGaps` if none exists, and the loop moves on.
    `verify_records` re-surfaces every blocked unit at the coverage gate, so nothing
    marked here is silently dropped: a blocked unit is an OPEN gap until an operator
    re-pends it or records an accepted disposition.
    """
    inv_rel = inventory.strip()
    unit_id = unit_id.strip()
    record_rel = record_path.strip()
    fallback = fallback.strip()

    if not inv_rel or not unit_id or not record_rel:
        logger.warning("inventory, unit_id, and record_path are all required")
        return MarkResult(mark_note="inventory, unit_id, and record_path are all required")

    root = survey_repo_root()
    record_file = root / record_rel
    status = _record_status(record_file)
    note = "unit marked from its record's status"
    if status is None:
        # Give-up path: never wedge the loop — durably record the gap and move on.
        status = "blocked"
        reason = fallback or "assessment produced no valid finding record"
        if not record_file.is_file():
            _write_stub(record_file, unit_id, reason)
            note = "no record on disk — wrote a blocked stub carrying the reason"
            logger.warning(
                "unit '%s': no record on disk — wrote a blocked stub (%s)", unit_id, reason
            )
        else:
            note = (
                "record exists but is invalid — unit marked blocked; verify_records "
                "will re-surface it"
            )
            logger.warning("unit '%s': record exists but is invalid — marked blocked", unit_id)

    inv_path = root / inv_rel
    if not inv_path.is_file():
        logger.warning("inventory at %s could not be read", inv_rel)
        return MarkResult(
            unit_status=status, mark_note=f"inventory at {inv_rel} could not be read"
        )
    lst = wl.WorkList(wl.JsonBackend(inv_path, items_key="units"))
    try:
        hit = lst.mark(unit_id, status)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s could not be read", inv_rel)
        return MarkResult(
            unit_status=status, mark_note=f"inventory at {inv_rel} could not be read"
        )

    if hit:
        logger.info("unit '%s' marked '%s'", unit_id, status)
        return MarkResult(marked=True, unit_status=status, mark_note=note)

    logger.warning("unit '%s' not found in %s", unit_id, inv_rel)
    return MarkResult(
        unit_status=status, mark_note=f"unit '{unit_id}' not found in {inv_rel}"
    )


__all__ = ["SURVEY_SCHEME", "mark_unit", "select_next_unit"]
