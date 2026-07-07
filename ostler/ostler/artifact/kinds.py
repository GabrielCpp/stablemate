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
    }


def _qa_evidence_vet(data: Any, spec_dir: Path, root: Path) -> list[str]:  # noqa: C901
    if not isinstance(data, dict):
        return ["qa-evidence.json must be a JSON object."]
    problems: list[str] = []

    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return [
            "no non-empty 'criteria' array "
            f"(found keys: {sorted(data.keys())}) — one entry per acceptance criterion with "
            "{'id', 'kind', 'verdict', 'evidence'} is required."
        ]

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

    # Run-id coherence (opt-in: enforced only when the QA pass stamped a runId).
    run_id = str(data.get("runId", "")).strip()
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
                basenames = {
                    Path(str(a).strip()).name
                    for a in (manifest.get("artifacts") or [])
                    if _is_nonempty_str(a)
                }
                for c in criteria:
                    if not isinstance(c, dict) or str(c.get("verdict", "")).strip().lower() != "pass":
                        continue
                    cid = str(c.get("id") or c.get("title") or "?")
                    evidence = c.get("evidence") or []
                    if isinstance(evidence, str):
                        evidence = [evidence]
                    if not any(Path(str(e).strip()).name in basenames for e in evidence):
                        problems.append(
                            f"{cid}: no cited evidence file appears in this run's manifest "
                            f"(runId {run_id}) — every Pass criterion must cite at least one "
                            f"artifact produced by the current execution."
                        )

    return problems


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
