"""Reading the `qa-run.ndjson` log a session wrote: its records, the run it opened, and which asserts pass, fail or abort an item."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_log_tally(spec_dir: Path) -> tuple[int, int]:
    """(passing, failing) assertion counts from ``qa/qa-run.ndjson`` — the runner's ground truth."""
    log_path = spec_dir / "qa" / "qa-run.ndjson"
    if not log_path.is_file():
        return (0, 0)
    passed = failed = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("kind") != "assert":
            continue
        result = str(rec.get("result", "")).strip().upper()
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
    return (passed, failed)


def latest_session_run_id(spec_dir: Path) -> str:
    """The runId the newest ``session_start`` in the run log opened with; "" if there is none."""
    log_path = spec_dir / "qa" / "qa-run.ndjson"
    if not log_path.is_file():
        return ""
    run_id = ""
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("kind") == "session_start":
            run_id = str(record.get("run_id", "")).strip()
    return run_id


def strict_ndjson(path: Path, problems: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"qa_run_log line {number} is invalid JSON ({exc}).")
            continue
        if not isinstance(record, dict):
            problems.append(f"qa_run_log line {number} is not an object.")
            continue
        records.append(record)
    return records


def relative_evidence_path(value: Any, spec_dir: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    path = Path(value)
    resolved = (path if path.is_absolute() else spec_dir / path).resolve()
    try:
        return resolved.relative_to(spec_dir.resolve()).as_posix()
    except ValueError:
        return ""


def passing_log_ref(ref: str, item_id: str, records: list[dict[str, Any]]) -> bool:
    parts = ref.rsplit(":assert:", 1)
    if len(parts) != 2:
        return False
    scenario, action = parts
    return any(
        record.get("kind") == "assert"
        and record.get("result") == "PASS"
        and record.get("scenario") == scenario
        and str(record.get("action", "")) == action
        and item_id in record.get("covers", [])
        for record in records
    )


def failing_log_refs(
    item_id: str, records: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """The failing `scenario:assert:action` refs covering `item_id`, split in two."""
    failing: list[str] = []
    aborted: list[str] = []
    for record in records:
        if (
            record.get("kind") != "assert"
            or record.get("result") == "PASS"
            or item_id not in record.get("covers", [])
        ):
            continue
        ref = f"{record.get('scenario', '?')}:assert:{record.get('action', '?')}"
        (aborted if record.get("sentinel") else failing).append(ref)
    return failing, aborted
