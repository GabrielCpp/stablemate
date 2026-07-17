#!/usr/bin/env python3
"""Hard, deterministic validator for one unit's finding record.

The finding record is the per-unit "note it" file — the durable, structured result of
one bounded assessment, and the ONLY thing the partitioner ever reads (compression
before synthesis: clustering happens over records, never over code). This validator
keeps the assessor honest so the partition and the emitted backlog can trust the
records. Concern-neutral by design: nothing stack-shaped, nothing concern-shaped —
``remediation_pattern`` values are emergent per initiative (proposed by assessors,
normalized during partitioning), so the schema stays closed while the taxonomy stays
open.

Record shape (markdown + YAML front-matter, mirroring author's knowledge records)::

    ---
    type: survey-finding
    unit: src/lib/components/DatePicker    # id from the inventory — must match
    kind: folder
    status: assessed | clean | blocked
    findings:                              # assessed: at least one
      - description: ...
        remediation_pattern: <kebab-slug>
        effort: trivial | small | substantial
        evidence: ...                      # file:line refs, observed behaviour
    openGaps: [...]                        # blocked: why the unit cannot be assessed
    disposition: accepted                  # blocked only: operator accepted the gap
    ---
    <free prose for humans — not parsed>

Checks: the file parses, ``unit`` matches the inventory id it was selected for,
``status`` is one of the three, an ``assessed`` record carries at least one complete
finding, a ``clean`` record carries none (a clean unit with findings is a
contradiction), and a ``blocked`` record names its gap in ``openGaps`` (mirrors
``openGaps`` in knowledge records — never a bare shrug).

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  record_path : repo-relative path to the finding record
    argv[2]  unit_id     : the inventory unit id this record must describe

Outputs JSON: {"record_ok": "yes"|"no", "record_errors": "<newline-joined>"}
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

_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
_PATTERN_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

RECORD_STATUSES = {"assessed", "clean", "blocked"}
EFFORTS = {"trivial", "small", "substantial"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def load_record(text: str) -> dict:
    """Parse the YAML front-matter of a finding record. Raises ValueError when malformed."""
    if not text.lstrip().startswith("---"):
        raise ValueError("record has no leading `---` YAML front-matter block")
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        raise ValueError("YAML front-matter block is not closed by a second `---` fence")
    if yaml is None:
        raise ValueError("PyYAML is required to parse finding records but is unavailable")
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML front-matter is not valid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("front-matter must be a mapping")
    return data


def check_record(record: dict, unit_id: str) -> list[str]:
    """All structural errors in a parsed record (shared with verify-records.py's copy)."""
    errors: list[str] = []

    if record.get("type") != "survey-finding":
        errors.append("`type` must be `survey-finding`")
    unit = str(record.get("unit") or "").strip()
    if unit != unit_id:
        errors.append(f"`unit` is '{unit or '?'}' but this record was selected for "
                      f"'{unit_id}' — the record must describe its own inventory unit")

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
        if not _PATTERN_SLUG_RE.match(pattern):
            errors.append(f"findings[{i}] remediation_pattern '{pattern or '?'}' must be a "
                          f"kebab-case slug (the partitioner clusters on it)")
        if f.get("effort") not in EFFORTS:
            errors.append(f"findings[{i}] effort '{f.get('effort')}' not one of {sorted(EFFORTS)}")
        if not str(f.get("evidence") or "").strip():
            errors.append(f"findings[{i}] missing non-empty `evidence` — a finding with no "
                          f"file:line/observed-behaviour evidence is a guess, not a finding")

    if status == "assessed" and not findings:
        errors.append("status is `assessed` but `findings` is empty — use `clean` when there "
                      "is genuinely nothing to do")
    if status == "clean" and findings:
        errors.append("status is `clean` but the record carries findings — a clean unit with "
                      "findings is a contradiction; use `assessed`")

    open_gaps = record.get("openGaps")
    if status == "blocked":
        if not (isinstance(open_gaps, list) and open_gaps):
            errors.append("status is `blocked` but `openGaps` is empty — record WHY the unit "
                          "cannot be assessed (the operator gate reads this)")
    disposition = record.get("disposition")
    if disposition is not None:
        if disposition != "accepted":
            errors.append(f"`disposition` '{disposition}' — the only recognized value is "
                          f"`accepted` (an operator accepting a blocked unit's gap)")
        elif status != "blocked":
            errors.append("`disposition: accepted` only makes sense on a `blocked` record")

    return errors


def main(logger: logging.Logger) -> None:
    record_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    unit_id = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""

    def emit(ok: bool, errors: list[str]) -> None:
        print(json.dumps({"record_ok": "yes" if ok else "no",
                          "record_errors": "\n".join(errors)}))

    if not record_rel or not unit_id:
        logger.warning("record_path and unit_id are both required")
        emit(False, ["record_path and unit_id are both required"])
        return

    root = find_repo_root()
    record_path = (root / record_rel).resolve()
    if not record_path.is_file():
        logger.warning("finding record missing at %s — the assessor must write it", record_rel)
        emit(False, [f"finding record missing at {record_rel} — the assessor must write it"])
        return

    try:
        record = load_record(record_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        logger.warning("record %s could not be parsed: %s", record_rel, exc)
        emit(False, [f"record could not be parsed: {exc}"])
        return

    errors = check_record(record, unit_id)
    if errors:
        logger.warning("record %s failed validation with %d error(s)", record_rel, len(errors))
    else:
        logger.info("record %s for unit '%s' is valid", record_rel, unit_id)
    emit(not errors, errors)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-record"))
