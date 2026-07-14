"""Built-in artifact kinds: filename, scaffold skeleton, and semantic vet rules.

Each kind's ``vet`` returns a list of actionable problem strings (empty = clean).
Rules deliberately go beyond JSON Schema: file existence, cross-field
consistency, run-manifest coherence — the checks a producing agent must satisfy
before its artifact is trusted by a downstream deterministic consumer.

Workspace-specific checks (e.g. "does services[].repo resolve in the developer's
multi-repo workspace") intentionally stay in the calling workflow, which owns
that context; ostler validates everything knowable from the repository alone.
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ArtifactKind:
    name: str
    filename: str
    description: str
    scaffold: Callable[[], Any]
    vet: Callable[[Any, Path, Path], list[str]]  # (data, spec_dir, repo_root) -> problems


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _evidence_exists(ref: Any, root: Path, spec_dir: Path) -> bool:
    """Resolve an evidence reference against the likely roots (mirrors the QA gate)."""
    if not _is_nonempty_str(ref):
        return False
    ref = str(ref).strip()
    candidates = [Path(ref), root / ref, spec_dir / ref, spec_dir.parent / ref]
    return any(c.is_file() for c in candidates)


# ---------------------------------------------------------------------------
# plan-context.json
# ---------------------------------------------------------------------------

def _plan_context_scaffold() -> dict:
    return {
        "story": "<story-slug>",
        "services": [
            {
                "repo": "<workspace repo name>",
                "path": "<service dir, e.g. api or web>",
                "type": "<go | react-router | terraform | ...>",
                "plan_file": "plan.md",
                "skills": [],
            }
        ],
        "implementation_order": ["<repo>::<path>"],
    }


def _plan_context_vet(data: Any, spec_dir: Path, root: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["plan-context.json must be a JSON object."]
    problems: list[str] = []

    services = data.get("services")
    if not isinstance(services, list) or not services:
        return [
            "no non-empty 'services' array "
            f"(found keys: {sorted(data.keys())}) — every layer to implement must be declared as "
            "{'repo', 'path', 'type', 'plan_file', 'skills'}; keys like 'touched_layers' are not "
            "read by any consumer."
        ]

    declared: set[str] = set()
    for i, svc in enumerate(services):
        label = f"services[{i}]"
        if not isinstance(svc, dict):
            problems.append(f"{label}: not an object.")
            continue
        for field in ("repo", "path", "type"):
            if not _is_nonempty_str(svc.get(field)):
                problems.append(f"{label}: missing/empty '{field}'.")
        plan_file = svc.get("plan_file")
        if not _is_nonempty_str(plan_file):
            problems.append(f"{label}: missing/empty 'plan_file'.")
        elif not (spec_dir / str(plan_file)).is_file():
            problems.append(f"{label}: plan_file '{plan_file}' not found in {spec_dir}.")
        skills = svc.get("skills", [])
        if skills is not None and not isinstance(skills, list):
            problems.append(f"{label}: 'skills' must be a list when present.")
        if _is_nonempty_str(svc.get("repo")) and _is_nonempty_str(svc.get("path")):
            declared.add(f"{svc['repo']}::{svc['path']}")

    order = data.get("implementation_order")
    if order is not None:
        if not isinstance(order, list):
            problems.append("'implementation_order' must be a list when present.")
        else:
            for entry in order:
                if not _is_nonempty_str(entry) or "::" not in str(entry):
                    problems.append(
                        f"implementation_order entry {entry!r} is not '<repo>::<path>'."
                    )
                elif str(entry) not in declared:
                    problems.append(
                        f"implementation_order entry '{entry}' matches no declared service "
                        f"(declared: {sorted(declared)})."
                    )
    return problems


# ---------------------------------------------------------------------------
# qa-evidence.json
# ---------------------------------------------------------------------------

_CRITERION_KINDS = ("behavioral", "parity", "data-entry", "transient")


def _qa_evidence_scaffold() -> dict:
    return {
        "overall": "Pass | Fail | Blocked",
        "runId": "",
        "qa_run_log": "qa/qa-run.ndjson",
        "criteria": [
            {
                "id": "AC1",
                "title": "<criterion text>",
                "kind": "behavioral | parity | data-entry | transient",
                "verdict": "Pass | Fail",
                "evidence": ["docs/specs/<story>/qa/<file>"],
            }
        ],
        "visual_fidelity": [],
        "obligations": [],
    }


def _qa_evidence_vet(data: Any, spec_dir: Path, root: Path) -> list[str]:  # noqa: C901
    if not isinstance(data, dict):
        return ["qa-evidence.json must be a JSON object."]
    problems: list[str] = []

    criteria = data.get("criteria")
    obligations = data.get("obligations", [])
    if not isinstance(criteria, list):
        return [
            "no 'criteria' array "
            f"(found keys: {sorted(data.keys())}) — one entry per acceptance criterion with "
            "{'id', 'kind', 'verdict', 'evidence'} is required."
        ]
    if not isinstance(obligations, list):
        return ["'obligations' must be an array when present."]
    if not criteria and not obligations:
        return ["qa-evidence must contain at least one criterion or OKF obligation."]

    overall = str(data.get("overall", "")).strip().lower()
    any_fail = False

    for i, c in enumerate(criteria):
        if not isinstance(c, dict):
            problems.append(f"criterion #{i + 1} is not an object.")
            continue
        cid = str(c.get("id") or c.get("title") or f"#{i + 1}")
        kind = str(c.get("kind", "")).strip().lower()
        verdict = str(c.get("verdict", "")).strip().lower()

        if kind not in _CRITERION_KINDS:
            problems.append(f"{cid}: missing/invalid 'kind' (expected {'|'.join(_CRITERION_KINDS)}).")
        if verdict not in ("pass", "fail"):
            problems.append(f"{cid}: missing/invalid 'verdict' (expected Pass|Fail).")
            continue
        if verdict == "fail":
            any_fail = True
            continue

        evidence = c.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not [e for e in evidence if _evidence_exists(e, root, spec_dir)]:
            problems.append(
                f"{cid}: marked Pass but cites no evidence file that exists on disk "
                f"(evidence={evidence!r})."
            )

        if kind == "parity":
            checklist = c.get("checklist")
            if not isinstance(checklist, list) or not checklist:
                problems.append(
                    f"{cid}: parity criterion has no per-element 'checklist' — a parity Pass must "
                    f"enumerate every old-side element/state and confirm each."
                )
            else:
                for j, row in enumerate(checklist):
                    if not isinstance(row, dict):
                        problems.append(f"{cid}: checklist row #{j + 1} is not an object.")
                        continue
                    rv = str(row.get("verdict", "")).strip().lower()
                    if rv == "divergent":
                        problems.append(
                            f"{cid}: checklist element '{row.get('element', '?')}' is divergent — "
                            f"a parity divergence is a Fail even if no AC names it."
                        )
                    elif rv != "match":
                        problems.append(
                            f"{cid}: checklist element '{row.get('element', '?')}' has no clear "
                            f"match/divergent verdict."
                        )
                    if not _evidence_exists(row.get("evidence", ""), root, spec_dir):
                        problems.append(
                            f"{cid}: checklist element '{row.get('element', '?')}' cites no "
                            f"existing evidence file."
                        )

        if kind == "data-entry":
            p = c.get("persistence")
            if not isinstance(p, dict):
                problems.append(
                    f"{cid}: data-entry criterion has no 'persistence' proof — a Pass must show "
                    f"fill→save→reload with evidence."
                )
            else:
                if p.get("persisted") is not True:
                    problems.append(f"{cid}: persistence.persisted is not true.")
                if p.get("bled_to_others") is True:
                    problems.append(f"{cid}: persistence.bled_to_others is true — Save bled.")
                if not _evidence_exists(p.get("evidence", ""), root, spec_dir):
                    problems.append(f"{cid}: persistence cites no existing evidence file.")

        if kind == "transient":
            t = c.get("transient")
            if not isinstance(t, dict):
                problems.append(
                    f"{cid}: transient criterion has no 'transient' proof "
                    f"(trigger/appeared/disappeared/mid_window_capture)."
                )
            else:
                if t.get("appeared") is not True or t.get("disappeared") is not True:
                    problems.append(
                        f"{cid}: transient proof must show appeared=true AND disappeared=true."
                    )
                if not _evidence_exists(t.get("mid_window_capture", ""), root, spec_dir):
                    problems.append(f"{cid}: transient mid_window_capture file does not exist.")

    if overall == "pass" and any_fail:
        problems.append("overall is Pass but at least one criterion verdict is Fail — inconsistent.")

    # A pass is valid only when it is backed by the current runner-owned ledger.
    run_id = str(data.get("runId", "")).strip()
    if overall == "pass" and not run_id:
        problems.append("overall Pass requires a non-empty runner-produced runId.")
    if run_id:
        manifest_path = spec_dir / "qa" / "run-manifest.json"
        if not manifest_path.is_file():
            problems.append(
                f"runId '{run_id}' is claimed but qa/run-manifest.json is missing — write the "
                f"manifest listing every artifact this run produced."
            )
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                manifest = None
                problems.append(f"qa/run-manifest.json is not valid JSON ({exc}).")
            if isinstance(manifest, dict):
                if str(manifest.get("runId", "")).strip() != run_id:
                    problems.append(
                        f"run-manifest runId '{manifest.get('runId')}' does not match "
                        f"qa-evidence runId '{run_id}' — evidence and summary must come from "
                        f"the same execution."
                    )
                artifacts: dict[str, dict[str, Any]] = {}
                for artifact in manifest.get("artifacts") or []:
                    if not isinstance(artifact, dict) or not _is_nonempty_str(artifact.get("path")):
                        problems.append("run-manifest artifacts must be objects with path and sha256.")
                        continue
                    path = str(artifact["path"]).strip()
                    artifacts[path] = artifact
                    resolved = (spec_dir / path).resolve()
                    if not resolved.is_relative_to(spec_dir.resolve()) or not resolved.is_file():
                        problems.append(f"manifest artifact '{path}' is missing or escapes spec_dir.")
                        continue
                    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
                    if artifact.get("sha256") != digest:
                        problems.append(f"manifest artifact '{path}' has a stale or invalid sha256.")

                log_ref = data.get("qa_run_log")
                if not _is_nonempty_str(log_ref):
                    problems.append("runId is present but qa_run_log is missing.")
                    records = []
                else:
                    log_path = (spec_dir / str(log_ref)).resolve()
                    if not log_path.is_relative_to(spec_dir.resolve()) or not log_path.is_file():
                        problems.append("qa_run_log is missing or escapes spec_dir.")
                        records = []
                    else:
                        records = _strict_ndjson(log_path, problems)
                        normalized_log = _relative_evidence_path(log_ref, spec_dir)
                        if normalized_log not in artifacts:
                            problems.append("qa_run_log is not registered in the current run manifest.")
                terminal = [record for record in records if record.get("kind") == "session_stop"]
                if not terminal or terminal[-1].get("run_id") != run_id:
                    problems.append("qa_run_log has no matching terminal session_stop record.")

                for row in [*criteria, *obligations]:
                    if not isinstance(row, dict) or str(row.get("verdict", "")).strip().lower() != "pass":
                        continue
                    item_id = str(row.get("id") or row.get("title") or "?")
                    evidence = row.get("evidence") or []
                    if isinstance(evidence, str):
                        evidence = [evidence]
                    normalized = [_relative_evidence_path(item, spec_dir) for item in evidence]
                    if not any(path in artifacts for path in normalized if path):
                        problems.append(
                            f"{item_id}: no cited evidence file appears by exact path in this "
                            f"run's manifest (runId {run_id})."
                        )
                    refs = row.get("log_refs") or []
                    if not isinstance(refs, list) or not refs:
                        problems.append(f"{item_id}: Pass requires at least one assertion log_ref.")
                        continue
                    for ref in refs:
                        if not _passing_log_ref(str(ref), item_id, records):
                            problems.append(
                                f"{item_id}: log_ref '{ref}' does not resolve to a passing "
                                "runner assertion covering this obligation."
                            )

    return problems


def _strict_ndjson(path: Path, problems: list[str]) -> list[dict[str, Any]]:
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


def _relative_evidence_path(value: Any, spec_dir: Path) -> str:
    if not _is_nonempty_str(value):
        return ""
    path = Path(str(value))
    resolved = (path if path.is_absolute() else spec_dir / path).resolve()
    try:
        return resolved.relative_to(spec_dir.resolve()).as_posix()
    except ValueError:
        return ""


def _passing_log_ref(ref: str, item_id: str, records: list[dict[str, Any]]) -> bool:
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


# ---------------------------------------------------------------------------
# backlog-items.json
# ---------------------------------------------------------------------------

def _backlog_items_scaffold() -> list:
    return []


def _backlog_items_vet(data: Any, spec_dir: Path, root: Path) -> list[str]:
    if not isinstance(data, list):
        return ["backlog-items.json must be a JSON array."]
    problems: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(data):
        label = f"item #{i + 1}"
        if not isinstance(item, dict):
            problems.append(f"{label}: not an object.")
            continue
        item_id = item.get("id")
        if not _is_nonempty_str(item_id):
            problems.append(f"{label}: missing/empty 'id'.")
        else:
            if not _KEBAB_RE.match(str(item_id)):
                problems.append(f"{label}: id '{item_id}' is not kebab-case.")
            if item_id in seen:
                problems.append(f"{label}: duplicate id '{item_id}'.")
            seen.add(str(item_id))
        if not _is_nonempty_str(item.get("description")):
            problems.append(f"{label}: missing/empty 'description'.")
    return problems


# ---------------------------------------------------------------------------

KINDS: dict[str, ArtifactKind] = {
    kind.name: kind
    for kind in (
        ArtifactKind(
            name="plan-context",
            filename="plan-context.json",
            description="Planner → implementation dispatcher: layers/services to implement.",
            scaffold=_plan_context_scaffold,
            vet=_plan_context_vet,
        ),
        ArtifactKind(
            name="qa-evidence",
            filename="qa-evidence.json",
            description="QA → deterministic evidence gate: per-criterion machine-checkable proof.",
            scaffold=_qa_evidence_scaffold,
            vet=_qa_evidence_vet,
        ),
        ArtifactKind(
            name="backlog-items",
            filename="backlog-items.json",
            description="Triage/QA → backlog drain: separate-scope discoveries.",
            scaffold=_backlog_items_scaffold,
            vet=_backlog_items_vet,
        ),
    )
}


def get_kind(name: str) -> ArtifactKind | None:
    return KINDS.get(name)
