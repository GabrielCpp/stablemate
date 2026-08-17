"""The coder's adapter onto ostler's QA API — the port of `scripts/qa_cli.py`.

Each helper drives one `ostler qa …` operation through the `Ostler` Python API and
normalizes it to the `(returncode, payload, stderr)` triple the calling nodes branch on.
The triple is kept rather than typed away: it is what an API reporting *ok / data / message*
actually yields, and the four callers each turn it into a different status by a different
rule. Typing it here would mean picking one of those rules and pushing the other three into
`if`s anyway.

Two things the script did are gone. `emit()` printed the workflow's JSON envelope, which a
node returns as a model instead; and `fresh_import("qa_cli", also_purge=("ostler",))` — the
YAML engine's way of getting a fresh `ostler` into a subprocess per node — is a plain import
now, because nodes run in the engine's process and there is nothing to purge.

Library code, not nodes: `qa_context` and `qa_context_validate` back `shared/okf.py`, which
`docs` and `qa` share; `qa_lint`, `qa_validate` and `qa_run` back the QA flow's plan gate and
runner; `artifact_vet` backs the evidence gate, which is the only caller that roots ostler at
the repo rather than the docs tree.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler import Ostler

#: The plan file, relative to the story's spec dir. A Python module, not YAML: a scenario is
#: a function `ostler` executes under the project's own interpreter, so a wrong key raises
#: where a `jq` filter over a missing field used to pass vacuously.
QA_PLAN_FILE = "qa_plan.py"


def okf(docs_root: Path | None = None) -> Ostler:
    """An `Ostler` rooted at `docs_root`, or one that discovers its own root."""
    return Ostler(docs_root) if docs_root is not None else Ostler()


def parse_source_roots(source_roots: list[str]) -> dict[str, list[str]]:
    """`["SURFACE=PATH", …]` → `{surface: [path, …]}` (the CLI's `--source-root`)."""
    parsed: dict[str, list[str]] = {}
    for raw in source_roots:
        if isinstance(raw, str) and "=" in raw:
            surface, path = raw.split("=", 1)
            parsed.setdefault(surface.strip(), []).append(path.strip())
    return parsed


def qa_context(
    spec_dir: str,
    *,
    base: str,
    head: str,
    features_root: str,
    story_file: str,
    source_roots: list[str],
    docs_root: Path | None = None,
    exclude_paths: list[str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa context` → the obligation packet; rc=1 on an error-level finding.

    `exclude_paths` are repo-relative paths the caller has established are not part of the
    change under examination — see `shared/worktree.py` for the only thing that populates it.
    """
    try:
        packet = okf(docs_root).qa_context(
            base=base,
            head=head,
            spec=spec_dir,
            source_roots=parse_source_roots(source_roots),
            features_root=features_root,
            story_file=story_file or None,
            exclude_paths=exclude_paths or (),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return 1, {}, str(exc)
    has_error = any(f.get("severity") == "error" for f in packet.get("healthFindings", []))
    return (1 if has_error else 0), packet, ""


def qa_context_validate(
    spec_dir: str, *, docs_root: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa context-validate` → `{status, problems}`; rc=1 when problems exist."""
    try:
        problems = okf(docs_root).qa_context_validate(spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid", "problems": [str(exc)]}, str(exc)
    payload = {"status": "passed" if not problems else "invalid", "problems": problems}
    return (0 if not problems else 1), payload, ""


def qa_lint(
    plan: str, spec_dir: str, *, docs_root: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa lint` → the outcome data; rc=0 iff the plan's AST passes the allowlist."""
    try:
        outcome = okf(docs_root).qa_lint(plan, spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid"}, str(exc)
    return (0 if outcome.ok else 1), outcome.data, "" if outcome.ok else outcome.message


def qa_validate(
    plan: str, spec_dir: str, *, docs_root: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa validate` → the outcome data; rc=0 iff the plan is valid."""
    try:
        outcome = okf(docs_root).qa_validate(plan, spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid"}, str(exc)
    return (0 if outcome.ok else 1), outcome.data, "" if outcome.ok else outcome.message


def qa_tools_catalog(*, docs_root: Path | None = None) -> tuple[int, dict[str, Any], str]:
    """`ostler qa tools list` → `{tools, errors}`; rc=1 when any opted-in tool fails to resolve."""
    try:
        payload = okf(docs_root).qa_tools_catalog()
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"tools": [], "errors": [str(exc)]}, str(exc)
    return (1 if payload.get("errors") else 0), payload, ""


def qa_run(
    plan: str, spec_dir: str, *, docs_root: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    """`ostler qa run` → the four-state outcome data; rc=0 iff the run passed."""
    try:
        outcome = okf(docs_root).qa_run(plan, spec=spec_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return 1, {"status": "invalid"}, str(exc)
    return (0 if outcome.ok else 1), outcome.data, "" if outcome.ok else outcome.message


def artifact_vet(
    kind: str, spec_dir: str, *, root: Path
) -> tuple[int, dict[str, Any], str]:
    """`ostler artifact vet` → the outcome dict; rc=1 when it reports problems.

    `root` is the **repo** root, not the docs root, which is the one place in this module
    that is true — `verify_qa_evidence.py` built its `Ostler` from `find_repo_root()` and
    the artifact it vets (`<spec_dir>/qa-evidence.json`) is resolved against that. Kept as
    the script had it rather than harmonized with the other four helpers, because the two
    roots differ on a docs checkout and the gate would then vet nothing.

    A contract that cannot be evaluated cannot validate a pass, so the caller treats a
    non-empty `stderr` as a problem in its own right rather than as an absence of problems.
    """
    try:
        vetted = okf(root).artifact_vet(kind, spec_dir)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        return 1, {}, str(exc)
    return (1 if vetted.get("problems") else 0), vetted, ""


#: The runner's per-assertion log, relative to whichever directory the run wrote into —
#: `<spec_dir>/qa/` for the scored run, `<spec_dir>/qa-dry-run/<scenario>/` for a dry one.
QA_RUN_LOG = "qa-run.ndjson"


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


def notes_for(payload: dict[str, Any], stderr: str, fallback: str) -> str:
    """Concise routing notes off the packet, keeping the deterministic diagnostics."""
    for key in ("notes", "message", "problems", "errors", "healthFindings"):
        value = payload.get(key)
        if value:
            if isinstance(value, str):
                return value
            return json.dumps(value, sort_keys=True)
    return stderr or fallback


__all__ = [
    "artifact_vet",
    "assert_records",
    "failed_assertions",
    "notes_for",
    "okf",
    "parse_source_roots",
    "qa_context",
    "qa_context_validate",
    "qa_lint",
    "qa_run",
    "qa_tools_catalog",
    "qa_validate",
    "scored_run_log",
]
