"""What the coder's QA nodes need *around* an ostler call.

The `(returncode, payload, stderr)` adapter that used to live here is gone: `Ostler`'s
qa and artifact methods answer in `QaOutcome` — `ok`, `message`, `data`, `status` — so a
node calls the API directly and reads the field it actually branches on. A wrapper that
flattened three fields into a returncode only to have each of five callers unflatten it
by its own rule was work with no reader.

What is left is the part that is not ostler's: the run-log parse both gates share, the
`--source-root` string form the workflow carries, and the routing notes a node hands to
the model when a check comes back red.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler.qa import QaOutcome

#: The plan file, relative to the story's spec dir. A Python module, not YAML: a scenario is
#: a function `ostler` executes under the project's own interpreter, so a wrong key raises
#: where a `jq` filter over a missing field used to pass vacuously.
QA_PLAN_FILE = "qa_plan.py"

#: The runner's per-assertion log, relative to whichever directory the run wrote into —
#: `<spec_dir>/qa/` for the scored run, `<spec_dir>/qa/<scenario>/` for a dry one.
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
    """Every `kind == "assert"` record in one `qa-run.ndjson`, in the order it was written.

    The run log is the only account of an assertion that no later turn can edit: the
    assessor writes `qa-evidence.json`, the runner writes this. Both the evidence gate and
    the dry-run gate read it, which is why the parse lives here rather than in either.

    A malformed line is skipped rather than raised on. The file is append-only NDJSON a
    killed run can leave half-written, and one truncated tail is not a reason to lose the
    hundred records before it.
    """
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
    """Concise routing notes off an outcome, keeping the deterministic diagnostics.

    The data the check produced comes first — findings and problem lists are what a repair
    turn can act on — then the outcome's own message, which is only informative when the
    check came back red (on a pass it says "wrote …", not why anything holds).
    """
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
