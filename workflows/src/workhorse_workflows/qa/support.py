"""What a QA node needs *around* an ostler call — shared by every family that runs one."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler.qa import QaOutcome

QA_PLAN_FILE = "qa_plan.py"

QA_RUN_LOG = "qa-run.ndjson"


def parse_source_roots(source_roots: list[str]) -> dict[str, list[str]]:
    """`["SURFACE=PATH", …]` → `{surface: [path, …]}` (the CLI's `--source-root`)."""
    parsed: dict[str, list[str]] = {}
    for raw in source_roots:
        if isinstance(raw, str) and "=" in raw:
            surface, path = raw.split("=", 1)
            parsed.setdefault(surface.strip(), []).append(path.strip())
    return parsed


def assert_records(log_path: Path) -> list[dict[str, Any]]:
    """Every `kind == "assert"` record in one `qa-run.ndjson`, in the order it was written."""
    if not log_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("kind") == "assert":
            records.append(record)
    return records


def failed_assertions(log_path: Path) -> dict[str, list[str]]:
    """`scenario -> ids of its assertions the run recorded as FAIL`, from one run log."""
    failures: dict[str, list[str]] = {}
    for record in assert_records(log_path):
        if str(record.get("result", "")).strip().upper() != "FAIL":
            continue
        scenario = str(record.get("scenario", "")).strip()
        if not scenario:
            continue
        failures.setdefault(scenario, []).append(str(record.get("id") or "?"))
    return failures


def scored_run_log(spec_dir: Path) -> Path:
    """The scored run's log — the one `run_qa_plan` writes and the evidence gate reads."""
    return spec_dir / "qa" / QA_RUN_LOG


def notes_for(outcome: QaOutcome, fallback: str) -> str:
    """Concise routing notes off an outcome, keeping the deterministic diagnostics."""
    for key in ("notes", "message", "problems", "errors", "healthFindings"):
        value = outcome.data.get(key)
        if value:
            if isinstance(value, str):
                return value
            return json.dumps(value, sort_keys=True)
    if not outcome.ok and outcome.message:
        return outcome.message
    return fallback


__all__ = [
    "QA_PLAN_FILE",
    "QA_RUN_LOG",
    "assert_records",
    "failed_assertions",
    "notes_for",
    "parse_source_roots",
    "scored_run_log",
]
