"""Finding records: one checked hard on its own, then all of them checked together.

The finding record is the per-unit "note it" file — the durable, structured result of one
bounded assessment, and the ONLY thing the partitioner ever reads. Clustering happens over
records, never over code, so these two gates are what let the partition and the emitted
backlog trust them.

`validate_record` keeps one assessor honest. `verify_records` is the coverage gate: it runs
when the loop finds nothing pending and turns "the empty select IS the proof" into an
auditable claim, catching every way that claim rots — a re-pended unit, a missing or
contradictory record, a blocked unit nobody owns, or a unit dropped out of the frozen list
since the last commit.

Ported from `surveyor/scripts/{validate-record,verify-records}.py`. Those two scripts each
carried a copy of the same ruleset **with different message wording** — the strict one is
addressed to the assessor being asked to fix its own record, the compact one to an operator
reading a coverage report. Parity means keeping both wordings, so `check_record` and
`record_errors` are both here rather than deduplicated into one.
"""
from __future__ import annotations

import json
import logging
import re

import yaml
from workhorse_workflows.author.nodes.survey._blueprint import blueprint
from workhorse_workflows.author.nodes.survey import _stubs
from workhorse_workflows.author.nodes.survey.inventory import UNIT_STATUSES, record_slug
from workhorse_workflows.author.paths import survey_repo_root
from workhorse_workflows.author.schemas.survey import RecordCheck, VerifyResult
from workhorse_workflows.kit import show_file

#: A record is markdown with a leading YAML front-matter fence.
FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
#: `remediation_pattern` values are emergent per initiative — proposed by assessors,
#: normalized during partitioning — so the schema stays closed while the taxonomy stays
#: open. All it enforces is the shape the partitioner clusters on.
PATTERN_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
#: The statuses a finding record may declare.
RECORD_STATUSES = {"assessed", "clean", "blocked"}
#: How much work one finding is. Concern-neutral: nothing stack-shaped in here.
EFFORTS = {"trivial", "small", "substantial"}


def load_record(text: str) -> dict:
    """Parse a record's YAML front-matter. Raises ValueError when malformed."""
    if not text.lstrip().startswith("---"):
        raise ValueError("record has no leading `---` YAML front-matter block")
    m = FRONT_MATTER_RE.match(text)
    if not m:
        raise ValueError("YAML front-matter block is not closed by a second `---` fence")
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML front-matter is not valid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("front-matter must be a mapping")
    return data


def check_record(record: dict, unit_id: str) -> list[str]:
    """Every structural error in a parsed record, worded for the assessor fixing it."""
    errors: list[str] = []

    if record.get("type") != "survey-finding":
        errors.append("`type` must be `survey-finding`")
    unit = str(record.get("unit") or "").strip()
    if unit != unit_id:
        errors.append(
            f"`unit` is '{unit or '?'}' but this record was selected for "
            f"'{unit_id}' — the record must describe its own inventory unit"
        )

    status = record.get("status")
    if status not in RECORD_STATUSES:
        errors.append(f"`status` '{status}' not one of {sorted(RECORD_STATUSES)}")

    findings = record.get("findings")
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        errors.append("`findings` must be a list")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] is not a mapping")
            continue
        if not str(f.get("description") or "").strip():
            errors.append(f"findings[{i}] missing non-empty `description`")
        pattern = str(f.get("remediation_pattern") or "").strip()
        if not PATTERN_SLUG_RE.match(pattern):
            errors.append(
                f"findings[{i}] remediation_pattern '{pattern or '?'}' must be a "
                f"kebab-case slug (the partitioner clusters on it)"
            )
        if f.get("effort") not in EFFORTS:
            errors.append(
                f"findings[{i}] effort '{f.get('effort')}' not one of {sorted(EFFORTS)}"
            )
        if not str(f.get("evidence") or "").strip():
            errors.append(
                f"findings[{i}] missing non-empty `evidence` — a finding with no "
                f"file:line/observed-behaviour evidence is a guess, not a finding"
            )

    if status == "assessed" and not findings:
        errors.append(
            "status is `assessed` but `findings` is empty — use `clean` when there "
            "is genuinely nothing to do"
        )
    if status == "clean" and findings:
        errors.append(
            "status is `clean` but the record carries findings — a clean unit with "
            "findings is a contradiction; use `assessed`"
        )

    open_gaps = record.get("openGaps")
    if status == "blocked" and not (isinstance(open_gaps, list) and open_gaps):
        errors.append(
            "status is `blocked` but `openGaps` is empty — record WHY the unit "
            "cannot be assessed (the operator gate reads this)"
        )
    disposition = record.get("disposition")
    if disposition is not None:
        if disposition != "accepted":
            errors.append(
                f"`disposition` '{disposition}' — the only recognized value is "
                f"`accepted` (an operator accepting a blocked unit's gap)"
            )
        elif status != "blocked":
            errors.append("`disposition: accepted` only makes sense on a `blocked` record")

    return errors


def record_errors(record: dict, unit_id: str) -> list[str]:
    """The same ruleset, worded compactly for one line of a coverage report."""
    errors: list[str] = []
    if record.get("type") != "survey-finding":
        errors.append("`type` must be `survey-finding`")
    if str(record.get("unit") or "").strip() != unit_id:
        errors.append(f"`unit` does not match inventory id '{unit_id}'")
    status = record.get("status")
    if status not in RECORD_STATUSES:
        errors.append(f"`status` '{status}' not one of {sorted(RECORD_STATUSES)}")
    findings = record.get("findings") or []
    if not isinstance(findings, list):
        errors.append("`findings` must be a list")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] is not a mapping")
            continue
        if not str(f.get("description") or "").strip():
            errors.append(f"findings[{i}] missing `description`")
        if not PATTERN_SLUG_RE.match(str(f.get("remediation_pattern") or "")):
            errors.append(f"findings[{i}] `remediation_pattern` must be a kebab-case slug")
        if f.get("effort") not in EFFORTS:
            errors.append(
                f"findings[{i}] effort '{f.get('effort')}' not one of {sorted(EFFORTS)}"
            )
        if not str(f.get("evidence") or "").strip():
            errors.append(f"findings[{i}] missing `evidence`")
    if status == "assessed" and not findings:
        errors.append("status `assessed` with no findings — should be `clean`")
    if status == "clean" and findings:
        errors.append("status `clean` with findings — contradiction")
    gaps = record.get("openGaps")
    if status == "blocked" and not (isinstance(gaps, list) and gaps):
        errors.append("status `blocked` with empty `openGaps`")
    return errors


@blueprint.node(stub=_stubs.recorded)
def validate_record(logger: logging.Logger, record_path: str, unit_id: str) -> RecordCheck:
    """Check one unit's finding record, hard and deterministically.

    Nothing here is a judgment call: the record parses, it describes the unit it was
    selected for, its status is one of the three, an `assessed` record carries at least
    one complete finding, a `clean` one carries none, and a `blocked` one names its gap —
    never a bare shrug.
    """
    record_rel = record_path.strip()
    unit_id = unit_id.strip()

    if not record_rel or not unit_id:
        logger.warning("record_path and unit_id are both required")
        return RecordCheck(record_errors="record_path and unit_id are both required")

    root = survey_repo_root()
    path = (root / record_rel).resolve()
    if not path.is_file():
        logger.warning(
            "finding record missing at %s — the assessor must write it", record_rel
        )
        return RecordCheck(
            record_errors=(
                f"finding record missing at {record_rel} — the assessor must write it"
            )
        )

    try:
        record = load_record(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        logger.warning("record %s could not be parsed: %s", record_rel, exc)
        return RecordCheck(record_errors=f"record could not be parsed: {exc}")

    errors = check_record(record, unit_id)
    if errors:
        logger.warning(
            "record %s failed validation with %d error(s)", record_rel, len(errors)
        )
        return RecordCheck(record_errors="\n".join(errors))
    logger.info("record %s for unit '%s' is valid", record_rel, unit_id)
    return RecordCheck(record_ok=True)


@blueprint.node(stub=_stubs.verified)
def verify_records(
    logger: logging.Logger,
    inventory: str = "docs/survey/inventory.json",
    findings_dir: str = "docs/survey/findings",
    ref: str = "HEAD",
) -> VerifyResult:
    """The coverage gate: every frozen unit accounted for, and no silent shrinkage.

    The per-unit loop's empty select is the proof; this makes it auditable. The last check
    is reconcile-shaped and fail-open: a unit present in the last *committed* inventory
    but absent now, with no split lineage, is a frozen-list drop and therefore a
    regression — but with no git and no committed baseline there is nothing to compare, so
    that check skips rather than inventing a verdict.
    """
    inv_rel = inventory.strip() or "docs/survey/inventory.json"
    findings_rel = findings_dir.strip() or "docs/survey/findings"
    ref = ref.strip() or "HEAD"

    root = survey_repo_root()
    inv_path = root / inv_rel
    if not inv_path.is_file():
        logger.info("no inventory at %s — nothing was surveyed", inv_rel)
        return VerifyResult(
            holds=True,
            nothing_surveyed=True,
            verify_report=f"no inventory at {inv_rel} — nothing was surveyed",
        )
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
        units = data.get("units")
        if not isinstance(units, list):
            raise ValueError("`units` is not a list")
    except (json.JSONDecodeError, ValueError):
        logger.warning("inventory at %s is not parseable JSON with a `units` list", inv_rel)
        return VerifyResult(
            verify_errors=(
                f"inventory at {inv_rel} is not parseable JSON with a `units` list"
            ),
            verify_report="inventory unreadable",
        )

    errors: list[str] = []
    counts = {"assessed": 0, "clean": 0, "blocked": 0, "pending": 0}
    current_ids: set[str] = set()
    current_paths: list[str] = []

    for u in units:
        if not isinstance(u, dict) or not str(u.get("id") or ""):
            errors.append(f"  - [malformed-unit] inventory entry {u!r} has no id")
            continue
        unit_id = str(u["id"])
        current_ids.add(unit_id)
        current_paths.append(str(u.get("path") or unit_id))
        status = u.get("status")
        if status not in UNIT_STATUSES:
            errors.append(f"  - [bad-status] '{unit_id}' has status '{status}'")
            continue
        counts[status] += 1
        if status == "pending":
            errors.append(
                f"  - [pending] '{unit_id}' has not been assessed — the loop must "
                f"re-enter (this gate never waves a pending unit through)"
            )
            continue

        record_path = root / findings_rel / f"{record_slug(unit_id)}.md"
        if not record_path.is_file():
            errors.append(
                f"  - [missing-record] '{unit_id}' is '{status}' but has no finding "
                f"record at {findings_rel}/{record_slug(unit_id)}.md"
            )
            continue
        try:
            record = load_record(record_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"  - [invalid-record] '{unit_id}': {exc}")
            continue
        struct = record_errors(record, unit_id)
        if struct:
            errors.append(f"  - [invalid-record] '{unit_id}': " + "; ".join(struct))
            continue
        if record.get("status") != status:
            errors.append(
                f"  - [status-mismatch] '{unit_id}' is '{status}' in the inventory "
                f"but '{record.get('status')}' in its record — one claim, two files, "
                f"they must agree"
            )
            continue
        if status == "blocked" and record.get("disposition") != "accepted":
            gaps = "; ".join(str(g) for g in (record.get("openGaps") or []))[:300]
            errors.append(
                f"  - [blocked] '{unit_id}' is an OPEN gap ({gaps}) — fix the "
                f"precondition and set the unit's inventory status back to 'pending', "
                f"or record `disposition: accepted` (with the reason) in its record"
            )

    # ── Reconcile-style shrinkage vs the committed baseline ────────────────────────────
    base_text = show_file(root, ref, inv_rel)
    if base_text is not None:
        try:
            base_units = json.loads(base_text).get("units") or []
        except (json.JSONDecodeError, ValueError):
            base_units = []
        for bu in base_units:
            if not isinstance(bu, dict):
                continue
            bid = str(bu.get("id") or "")
            if not bid or bid in current_ids:
                continue
            bpath = str(bu.get("path") or bid)
            if any(p.startswith(bpath + "/") for p in current_paths):
                continue  # split lineage — the parent was replaced by its children
            errors.append(
                f"  - [dropped-unit] '{bid}' was in the committed inventory ({ref}) "
                f"but is gone now with no split lineage and no record — a frozen-list "
                f"drop is a regression; restore it or split it properly"
            )

    total = len(current_ids)
    report = (
        f"survey coverage: {total} unit(s) — {counts['assessed']} assessed, "
        f"{counts['clean']} clean, {counts['blocked']} blocked, "
        f"{counts['pending']} pending; {len(errors)} problem(s)"
    )
    if errors:
        logger.warning(report)
        return VerifyResult(
            verify_errors="\n".join(
                ["the survey's coverage claim does not hold yet:", *errors]
            ),
            verify_report=report,
        )
    logger.info(report)
    return VerifyResult(holds=True, verify_report=report)


__all__ = [
    "EFFORTS",
    "FRONT_MATTER_RE",
    "PATTERN_SLUG_RE",
    "RECORD_STATUSES",
    "check_record",
    "load_record",
    "record_errors",
    "validate_record",
    "verify_records",
]
