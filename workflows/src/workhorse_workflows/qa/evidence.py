"""The QA evidence gate: can the runner's claimed pass be checked, and does it check out?"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ostler import Ostler
from ostler.qa import REPORT_FILE, run_id_of

from workhorse_workflows.coder.shared.schemas.qa import QaResult, QaStatus
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.qa.support import QA_PLAN_FILE, failed_assertions, scored_run_log

EVIDENCE_FILE = "qa-evidence.json"

REPORT = REPORT_FILE

PASSTHROUGH_STATUSES: dict[str, QaStatus] = {
    "failed": "failed",
    "blocked": "blocked",
    "invalid": "invalid",
}

CRITERION_KINDS = ("behavioral", "parity", "data-entry", "transient")


def _run_log_tally(spec_dir: Path) -> tuple[int, int]:
    """`(passing, failing)` assertion counts from the QA run log (`qa/qa-run.ndjson`)."""
    log_path = spec_dir / "qa" / "qa-run.ndjson"
    if not log_path.is_file():
        return (0, 0)
    passed = failed = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("kind") != "assert":
            continue
        result = str(record.get("result", "")).strip().upper()
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
    return (passed, failed)


def _exists(ref: Any, root: Path, spec_dir: Path) -> bool:
    """Resolve an evidence reference against the likely roots and confirm it is a real file."""
    if not ref or not str(ref).strip():
        return False
    text = str(ref).strip()
    return any(
        candidate.is_file()
        for candidate in (Path(text), root / text, spec_dir / text, spec_dir.parent / text)
    )


def _artifact_problems(spec_dir: Path, data: dict) -> tuple[list[str], dict, dict]:
    """The four machine-owned files exist and parse, and the evidence points at the log."""
    problems: list[str] = []
    plan_path = spec_dir / QA_PLAN_FILE
    context_path = spec_dir / "qa-okf-context.json"
    log_path = spec_dir / "qa" / "qa-run.ndjson"
    manifest_path = spec_dir / "qa" / "run-manifest.json"

    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        problems.append(f"{QA_PLAN_FILE} is missing or empty.")

    context: dict = {}
    if not context_path.is_file():
        problems.append("qa-okf-context.json is missing.")
    else:
        try:
            parsed_context = json.loads(context_path.read_text(encoding="utf-8"))
            if isinstance(parsed_context, dict):
                context = parsed_context
            else:
                problems.append("qa-okf-context.json is not a JSON object.")
        except Exception as exc:
            problems.append(f"qa-okf-context.json is not valid JSON ({exc}).")

    if not log_path.is_file() or not log_path.read_text(encoding="utf-8").strip():
        problems.append("qa/qa-run.ndjson is missing or empty.")

    manifest: dict = {}
    if not manifest_path.is_file():
        problems.append("qa/run-manifest.json is missing.")
    else:
        try:
            parsed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(parsed_manifest, dict):
                manifest = parsed_manifest
            else:
                problems.append("qa/run-manifest.json is not a JSON object.")
        except Exception as exc:
            problems.append(f"qa/run-manifest.json is not valid JSON ({exc}).")

    if str(data.get("qa_run_log", "")).strip() != "qa/qa-run.ndjson":
        problems.append("qa-evidence.json must reference qa_run_log='qa/qa-run.ndjson'.")

    return problems, context, manifest


def _obligation_problems(context: dict, data: dict) -> list[str]:
    """Every obligation the OKF context *required* has a passing verdict with executed logs."""
    problems: list[str] = []
    evidence_obligations = data.get("obligations") if isinstance(data, dict) else None
    obligation_by_id = {
        str(item.get("id")): item
        for item in evidence_obligations or []
        if isinstance(item, dict) and item.get("id")
    }
    for obligation in context.get("obligations") or []:
        if not isinstance(obligation, dict) or not obligation.get("id"):
            continue
        if obligation.get("required", True) is False:
            continue
        obligation_id = str(obligation["id"])
        recorded = obligation_by_id.get(obligation_id)
        if not recorded:
            problems.append(f"{obligation_id}: required OKF obligation has no evidence verdict.")
            continue
        if str(recorded.get("verdict", "")).strip().lower() != "pass":
            problems.append(f"{obligation_id}: required OKF obligation did not pass.")
        if not recorded.get("log_refs"):
            problems.append(f"{obligation_id}: required OKF obligation has no executed log_refs.")
    return problems


def _parity_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]:
    """A parity Pass must enumerate every old-side element, and none may be divergent."""
    checklist = criterion.get("checklist")
    if not isinstance(checklist, list) or not checklist:
        return [
            f"{cid}: parity criterion has no per-element `checklist` — a parity Pass must "
            f"enumerate every old-side element/state (label, ✔/underline state indicator, "
            f"selection styling, control group, layout, values) and confirm each."
        ]
    problems: list[str] = []
    for index, row in enumerate(checklist):
        if not isinstance(row, dict):
            problems.append(f"{cid}: checklist row #{index + 1} is not an object.")
            continue
        verdict = str(row.get("verdict", "")).strip().lower()
        if verdict == "divergent":
            problems.append(
                f"{cid}: checklist element '{row.get('element', '?')}' is divergent — "
                f"a parity divergence is a Fail even if no AC names it."
            )
        elif verdict != "match":
            problems.append(
                f"{cid}: checklist element '{row.get('element', '?')}' has no clear "
                f"match/divergent verdict."
            )
        if not _exists(row.get("evidence", ""), root, spec_dir):
            problems.append(
                f"{cid}: checklist element '{row.get('element', '?')}' cites no existing "
                f"evidence file."
            )
    return problems


def _data_entry_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]:
    """A data-entry Pass must show fill→save→reload actually stuck, and stayed in its lane."""
    persistence = criterion.get("persistence")
    if not isinstance(persistence, dict):
        return [
            f"{cid}: data-entry criterion has no `persistence` proof — a Pass must show "
            f"fill→save→reload (before/after/reload, persisted, no bleed) with evidence."
        ]
    problems: list[str] = []
    if persistence.get("persisted") is not True:
        problems.append(
            f"{cid}: persistence.persisted is not true — the saved value was not "
            f"confirmed to survive reload."
        )
    if persistence.get("bled_to_others") is True:
        problems.append(
            f"{cid}: persistence.bled_to_others is true — Save wrote fields it should not."
        )
    if not _exists(persistence.get("evidence", ""), root, spec_dir):
        problems.append(f"{cid}: persistence proof cites no existing evidence file.")
    return problems


def _transient_problems(cid: str, criterion: dict, root: Path, spec_dir: Path) -> list[str]:
    """A transient Pass must catch the feedback mid-flight, not after it settled."""
    transient = criterion.get("transient")
    if not isinstance(transient, dict):
        return [
            f"{cid}: transient criterion has no `transient` proof — a Pass must show the "
            f"feedback (save flash/toast, inline validation, optimistic UI) APPEARED then "
            f"DISAPPEARED, with a capture taken inside the transient window."
        ]
    problems: list[str] = []
    if transient.get("appeared") is not True:
        problems.append(
            f"{cid}: transient.appeared is not true — the feedback was never observed "
            f"to appear after its trigger."
        )
    if transient.get("disappeared") is not True:
        problems.append(
            f"{cid}: transient.disappeared is not true — the appear-then-disappear "
            f"behavior was not confirmed (steady-state feedback is parity/behavioral, "
            f"not transient)."
        )
    if not _exists(transient.get("mid_window_capture", ""), root, spec_dir):
        problems.append(
            f"{cid}: transient criterion must cite a `mid_window_capture` taken while "
            f"the feedback was visible — a settled after-the-fact frame cannot prove a "
            f"transient (no existing mid-window capture file referenced)."
        )
    return problems


def _criteria_problems(criteria: list, root: Path, spec_dir: Path) -> list[str]:
    """Every criterion is well-formed, passing, and cites evidence that is really there."""
    problems: list[str] = []
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            problems.append(f"criterion #{index + 1} is not an object.")
            continue
        cid = str(criterion.get("id") or criterion.get("title") or f"#{index + 1}")
        kind = str(criterion.get("kind", "")).strip().lower()
        verdict = str(criterion.get("verdict", "")).strip().lower()

        if kind not in CRITERION_KINDS:
            problems.append(
                f"{cid}: missing/invalid `kind` (expected behavioral|parity|data-entry|transient)."
            )
        if verdict not in ("pass", "fail"):
            problems.append(f"{cid}: missing/invalid `verdict` (expected Pass|Fail).")

        if verdict == "fail":
            problems.append(f"{cid}: verdict is Fail — QA cannot pass overall while this AC fails.")
            continue
        if verdict != "pass":
            continue

        evidence = criterion.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not [ref for ref in evidence if _exists(ref, root, spec_dir)]:
            problems.append(
                f"{cid}: marked Pass but cites no evidence file that exists on disk "
                f"(evidence={evidence!r})."
            )

        if kind == "parity":
            problems.extend(_parity_problems(cid, criterion, root, spec_dir))
        if kind == "data-entry":
            problems.extend(_data_entry_problems(cid, criterion, root, spec_dir))
        if kind == "transient":
            problems.extend(_transient_problems(cid, criterion, root, spec_dir))
    return problems


def _unsupported_pass_problems(criteria: list, spec_dir: Path) -> list[str]:
    """A criterion may not be Pass while a scenario it rests on failed an assertion."""
    failures = failed_assertions(scored_run_log(spec_dir))
    if not failures:
        return []
    problems: list[str] = []
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            continue
        if str(criterion.get("verdict", "")).strip().lower() != "pass":
            continue
        cid = str(criterion.get("id") or criterion.get("title") or f"#{index + 1}")
        refs = criterion.get("log_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        scenarios = {str(ref).split(":assert:")[0].strip() for ref in refs}
        for scenario in sorted(scenarios & failures.keys()):
            failed = ", ".join(sorted(failures[scenario]))
            problems.append(
                f"{cid}: marked Pass but scenario `{scenario}` failed "
                f"{len(failures[scenario])} assertion(s) ({failed}) — a Pass cannot rest on "
                f"a scenario the run log records as failing, whatever `log_refs` cites."
            )
    return problems


def _visual_fidelity_problems(
    data: dict, root: Path, spec_dir: Path
) -> tuple[list[str], list[str]]:
    """Returns `(problems, vet_notes)` for the per-state `ostler vet` claims."""
    problems: list[str] = []
    vet_notes: list[str] = []
    visual_fidelity = data.get("visual_fidelity") if isinstance(data, dict) else None
    if not isinstance(visual_fidelity, list):
        return problems, vet_notes

    for index, entry in enumerate(visual_fidelity):
        if not isinstance(entry, dict):
            problems.append(f"visual_fidelity #{index + 1} is not an object.")
            continue
        state = str(entry.get("state") or f"#{index + 1}")
        report_ref = entry.get("report", "")
        report_path = None
        for candidate in (
            Path(str(report_ref)) if report_ref else None,
            root / str(report_ref) if report_ref else None,
            spec_dir / str(report_ref) if report_ref else None,
            spec_dir.parent / str(report_ref) if report_ref else None,
        ):
            if candidate is not None and candidate.is_file():
                report_path = candidate
                break
        if report_path is None:
            problems.append(
                f"visual_fidelity[{state}]: cites no existing report file (report={report_ref!r})."
            )
            continue

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"visual_fidelity[{state}]: report file is not valid JSON ({exc}).")
            continue

        summary = report.get("summary") if isinstance(report, dict) else None
        if not isinstance(summary, dict):
            problems.append(f"visual_fidelity[{state}]: report has no `summary` object.")
            continue

        missing_count = summary.get("missingCount", 0)
        if missing_count:
            missing = report.get("missing") or []
            selectors = [str(m.get("selector", "?")) for m in missing if isinstance(m, dict)]
            problems.append(
                f"visual_fidelity[{state}]: {missing_count} manifested element(s) did not "
                f"render — missing selector(s): {', '.join(selectors) or 'unknown'}."
            )
        else:
            vet_notes.append(
                f"{state}: matched={summary.get('matchedCount', 0)} "
                f"unexpected={summary.get('unexpectedCount', 0)} "
                f"unlabeled={summary.get('unlabeledCount', 0)} (informational only)."
            )
    return problems, vet_notes


def _report_problems(spec_dir: Path, data: dict) -> list[str]:
    """`qa-report.md` exists and was rendered from the run the evidence claims."""
    report_path = spec_dir / REPORT
    if not report_path.is_file():
        return [f"{REPORT} is missing — the runner writes it after every run; re-run QA."]
    run_id = str(data.get("runId", "")).strip()
    report_run_id = run_id_of(report_path)
    if report_run_id is None:
        return [f"{REPORT} carries no run marker — it was not rendered by `ostler qa report`."]
    if run_id and report_run_id != run_id:
        return [
            f"{REPORT} was rendered from run '{report_run_id}', not from the run the "
            f"evidence claims ('{run_id}') — the report and the evidence must come from "
            f"the same execution."
        ]
    return []


def _run_id_problems(data: dict, manifest: dict, criteria: list) -> list[str]:
    """Every Pass cites at least one artifact this execution actually produced."""
    run_id = str(data.get("runId", "")).strip()
    if not run_id:
        return ["qa-evidence.json has no runner-produced runId."]
    if not manifest:
        return []

    problems: list[str] = []
    manifest_run_id = str(manifest.get("runId") or manifest.get("run_id") or "").strip()
    if manifest_run_id != run_id:
        problems.append(
            f"run-manifest runId '{manifest_run_id}' does not match "
            f"qa-evidence runId '{run_id}' — the evidence and summary must come "
            f"from the same execution."
        )
    manifest_artifacts = [
        str(artifact.get("path") or artifact.get("file") or "").strip()
        if isinstance(artifact, dict)
        else str(artifact).strip()
        for artifact in manifest.get("artifacts") or []
    ]
    basenames = {os.path.basename(path) for path in manifest_artifacts if path}
    for criterion in criteria:
        if (
            not isinstance(criterion, dict)
            or str(criterion.get("verdict", "")).strip().lower() != "pass"
        ):
            continue
        cid = str(criterion.get("id") or criterion.get("title") or "?")
        evidence = criterion.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not any(os.path.basename(str(ref).strip()) in basenames for ref in evidence):
            problems.append(
                f"{cid}: no cited evidence file appears in this run's manifest "
                f"(runId {run_id}) — every Pass criterion must cite at least one "
                f"artifact produced by the current execution."
            )
    return problems


def verify_qa_evidence(
    logger: logging.Logger,
    spec_dir: str = "",
    claimed_status: str = "",
    claimed_notes: str = "",
    repo_dir: str = "",
) -> QaResult:
    """Check a claimed QA pass against the proof on disk; downgrade to `invalid` if it lies."""
    claimed = claimed_status.strip().lower()

    if claimed != "passed":
        status = PASSTHROUGH_STATUSES.get(claimed, "invalid")
        logger.info("claimed status '%s' is not 'passed' — passing through as '%s'", claimed, status)
        return QaResult(status=status, notes=claimed_notes)

    if not spec_dir:
        logger.warning("no spec_dir provided to locate qa-evidence.json")
        return QaResult(
            status="invalid",
            notes="QA evidence gate: no spec_dir provided to locate qa-evidence.json.",
        )

    root = find_repo_root(repo_dir)
    spec_path = root / spec_dir
    evidence_path = spec_path / EVIDENCE_FILE

    if not evidence_path.is_file():
        logger.warning("%s/%s is missing", spec_dir, EVIDENCE_FILE)
        return QaResult(
            status="invalid",
            notes=(
                f"QA evidence gate: {spec_dir}/{EVIDENCE_FILE} is missing. A claimed pass must "
                f"ship machine-checkable proof — write {EVIDENCE_FILE} with one entry per "
                f"acceptance criterion (id, kind, verdict, evidence[]; parity → per-element "
                f"checklist; data-entry → persistence proof) and re-run QA."
            ),
        )

    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("%s is not valid JSON: %s", EVIDENCE_FILE, exc)
        return QaResult(
            status="invalid",
            notes=f"QA evidence gate: {EVIDENCE_FILE} is not valid JSON ({exc}).",
        )

    criteria = data.get("criteria") if isinstance(data, dict) else None
    if not isinstance(criteria, list):
        criteria = []
    obligations = data.get("obligations") if isinstance(data, dict) else None
    if not isinstance(obligations, list):
        obligations = []

    if not criteria and not obligations:
        passed, failed = _run_log_tally(spec_path)
        if passed == 0 or failed > 0:
            logger.warning("%s has no criteria/obligations and no clean run-log proof", EVIDENCE_FILE)
            return QaResult(
                status="invalid",
                notes=(
                    f"QA evidence gate: {EVIDENCE_FILE} has neither `criteria` nor "
                    f"`obligations`, and the run log shows {passed} passing / {failed} failing "
                    f"assertion(s) — a claimed pass needs machine-checkable proof. For a UI "
                    f"story write acceptance criteria; for an infra/CLI story the QA plan's "
                    f"command assertions must all pass in the run log."
                ),
            )
        logger.info(
            "un-modeled surface (no OKF criteria/obligations): accepting on %d passing run-log "
            "assertion(s), 0 failures",
            passed,
        )

    problems, context, manifest = _artifact_problems(spec_path, data)

    vetted = Ostler(root).artifact_vet("qa-evidence", spec_dir)
    if vetted.data.get("error"):
        problems.append(
            f"[ostler] qa-evidence validation could not run ({vetted.data['error']})."
        )
    problems.extend(f"[ostler] {problem}" for problem in vetted.data.get("problems", []))

    overall = str(data.get("overall", "")).strip().lower()
    if overall and overall != "pass":
        problems.append(
            f"overall is '{data.get('overall')}' but the runner reported passed — inconsistent."
        )

    problems.extend(_obligation_problems(context, data))
    problems.extend(_criteria_problems(criteria, root, spec_path))
    problems.extend(_unsupported_pass_problems(criteria, spec_path))
    fidelity_problems, vet_notes = _visual_fidelity_problems(data, root, spec_path)
    problems.extend(fidelity_problems)
    problems.extend(_run_id_problems(data, manifest, criteria))
    problems.extend(_report_problems(spec_path, data))

    if problems:
        logger.warning("QA evidence gate invalidated this pass — %d problem(s)", len(problems))
        return QaResult(
            status="invalid",
            notes=(
                "QA evidence gate invalidated this pass — the machine-checkable proof is "
                "missing or self-contradictory. Fix and re-QA:\n- " + "\n- ".join(problems)
            ),
        )

    note = f"QA evidence gate: {len(criteria)} criteria validated (evidence files present, "
    note += "parity checklists enumerated, save-flows proven). "
    if vet_notes:
        note += "visual_fidelity: " + "; ".join(vet_notes) + ". "
    note += claimed_notes or ""
    logger.info("QA evidence gate passed: %d criteria validated", len(criteria))
    return QaResult(status="passed", notes=note.strip())


__all__ = ["verify_qa_evidence"]
