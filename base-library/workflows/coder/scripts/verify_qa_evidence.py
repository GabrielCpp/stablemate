#!/usr/bin/env python3
"""Deterministic QA evidence gate for runner-produced proof.

A prompt mandate ("diff every element, verify the save flow") cannot, by itself, guarantee
QA actually did it. This gate runs after ``ostler qa run`` and can only reject a runner pass.
Malformed/missing deterministic proof is ``invalid`` rather than a product failure. It enforces
that the machine-owned context, plan, ledger, manifest, and evidence are self-consistent:

  - QA wrote `<spec_dir>/qa-evidence.json` and it parses.
  - Its `overall` agrees with the agent's claimed status (no Pass-overall with a Fail criterion).
  - Every criterion has an id, a `kind`, and a verdict.
  - Every **Pass** criterion cites at least one evidence file that ACTUALLY EXISTS on disk.
  - Every **parity** criterion has a non-empty per-element `checklist`, each row with an existing
    evidence file and a verdict in {match, divergent}; a row marked `divergent` contradicts a Pass
    (→ downgrade) — "loaded the screenshot but didn't enumerate it" cannot pass.
  - Every **data-entry** criterion has a `persistence` block proving fill→save→reload actually
    stuck (`persisted: true`, `bled_to_others: false`) with an existing evidence file.
  - Every **transient** criterion (feedback that appears then clears — a save flash/toast, inline
    validation, optimistic UI) has a `transient` block proving the feedback was observed to APPEAR
    then DISAPPEAR (`appeared: true`, `disappeared: true`) and cites a `mid_window_capture` taken
    while it was visible — a settled after-the-fact frame cannot prove a transient.
  - Every `visual_fidelity` entry (a per-state `ostler vet` claim) cites a `report` file that
    exists and parses; a report's `summary.missingCount > 0` (a manifested element failed to
    render) downgrades the pass. `unexpectedCount`/`unlabeledCount` are logged as informational
    only — `ostler vet` exits nonzero for any disagreement bucket, and its `unlabeled` bucket
    conflates real gaps with legitimate role-less native elements, so only `missing` is a real
    regression signal (see `react-router-a11y/SKILL.md`).

If the claimed status is not ``passed``, the gate preserves all four statuses. If a check fails
on a runner pass, it emits ``invalid`` so routing returns to planning/context repair. An auditor
never gets an opportunity to upgrade invalid deterministic evidence.

Stdlib-only (runs under the system `python3`, like the other gate scripts).

Usage: verify_qa_evidence.py <spec_dir> <claimed_status> [claimed_notes]
Outputs JSON captured under the node's `qa_result` key:
  {"qa_result": {"status": "passed"|"failed"|"blocked"|"invalid", "notes": "..."}}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

EVIDENCE_FILE = "qa-evidence.json"


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def emit(status: str, notes: str) -> None:
    print(json.dumps({"qa_result": {"status": status, "notes": notes}}))
    sys.exit(0)


def evidence_exists(ref: str, root: Path, spec_dir: Path) -> bool:
    """Resolve an evidence reference against the likely roots and confirm it is a real file."""
    if not ref or not str(ref).strip():
        return False
    ref = str(ref).strip()
    candidates = [Path(ref), root / ref, spec_dir / ref, spec_dir.parent / ref]
    return any(c.is_file() for c in candidates)


def main(logger: logging.Logger) -> None:
    spec_dir_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    claimed_status = (sys.argv[2] if len(sys.argv) > 2 else "").strip().lower()
    claimed_notes = sys.argv[3] if len(sys.argv) > 3 else ""

    # Only a runner pass is eligible for evidence verification. Preserve the other
    # three machine statuses exactly; a missing status is itself invalid.
    if claimed_status != "passed":
        status = (
            claimed_status
            if claimed_status in {"failed", "blocked", "invalid"}
            else "invalid"
        )
        logger.info("claimed status '%s' is not 'passed' — passing through as '%s'", claimed_status, status)
        emit(status, claimed_notes)

    if not spec_dir_arg:
        logger.warning("no spec_dir provided to locate qa-evidence.json")
        emit(
            "invalid",
            "QA evidence gate: no spec_dir provided to locate qa-evidence.json.",
        )

    root = find_repo_root()
    spec_dir = root / spec_dir_arg
    evidence_path = spec_dir / EVIDENCE_FILE

    if not evidence_path.is_file():
        logger.warning("%s/%s is missing", spec_dir_arg, EVIDENCE_FILE)
        emit(
            "invalid",
            f"QA evidence gate: {spec_dir_arg}/{EVIDENCE_FILE} is missing. A claimed pass must "
            f"ship machine-checkable proof — write {EVIDENCE_FILE} with one entry per acceptance "
            f"criterion (id, kind, verdict, evidence[]; parity → per-element checklist; data-entry "
            f"→ persistence proof) and re-run QA.",
        )

    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse error fails the gate
        logger.warning("%s is not valid JSON: %s", EVIDENCE_FILE, exc)
        emit("invalid", f"QA evidence gate: {EVIDENCE_FILE} is not valid JSON ({exc}).")

    criteria = data.get("criteria") if isinstance(data, dict) else None
    if not isinstance(criteria, list) or not criteria:
        logger.warning("%s has no `criteria` array", EVIDENCE_FILE)
        emit("invalid", f"QA evidence gate: {EVIDENCE_FILE} has no `criteria` array.")

    problems: list[str] = []

    plan_path = spec_dir / "qa-plan.yml"
    context_path = spec_dir / "qa-okf-context.json"
    log_path = spec_dir / "qa" / "qa-run.ndjson"
    manifest_path = spec_dir / "qa" / "run-manifest.json"

    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        problems.append("qa-plan.yml is missing or empty.")

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
        except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
            problems.append(f"qa/run-manifest.json is not valid JSON ({exc}).")

    qa_run_log = str(data.get("qa_run_log", "")).strip()
    if qa_run_log != "qa/qa-run.ndjson":
        problems.append(
            "qa-evidence.json must reference qa_run_log='qa/qa-run.ndjson'."
        )

    # Apply Ostler's runner-aware artifact contract as a mandatory deterministic
    # check. It validates hashes, exact manifest paths, terminal ledger records,
    # and passing assertion refs. Missing/broken Ostler cannot validate a pass.
    try:
        import subprocess

        ostler_out = subprocess.run(
            [
                "ostler",
                "artifact",
                "vet",
                "qa-evidence",
                "--spec",
                spec_dir_arg,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(root),
        )
        if ostler_out.stdout.strip():
            parsed = json.loads(ostler_out.stdout)
            problems.extend(f"[ostler] {p}" for p in parsed.get("problems", []))
        else:
            problems.append("[ostler] qa-evidence validation returned no JSON output.")
    except Exception as exc:  # noqa: BLE001 - any validator failure invalidates proof
        problems.append(f"[ostler] qa-evidence validation could not run ({exc}).")

    overall = str(data.get("overall", "")).strip().lower()
    if overall and overall != "pass":
        problems.append(
            f"overall is '{data.get('overall')}' but the runner reported passed — inconsistent."
        )

    evidence_obligations = data.get("obligations") if isinstance(data, dict) else None
    obligation_by_id = {
        str(item.get("id")): item
        for item in evidence_obligations or []
        if isinstance(item, dict) and item.get("id")
    }
    for obligation in context.get("obligations") or []:
        if not isinstance(obligation, dict) or not obligation.get("id"):
            continue
        obligation_id = str(obligation["id"])
        recorded = obligation_by_id.get(obligation_id)
        if not recorded:
            problems.append(
                f"{obligation_id}: required OKF obligation has no evidence verdict."
            )
            continue
        if str(recorded.get("verdict", "")).strip().lower() != "pass":
            problems.append(f"{obligation_id}: required OKF obligation did not pass.")
        if not recorded.get("log_refs"):
            problems.append(
                f"{obligation_id}: required OKF obligation has no executed log_refs."
            )

    for i, c in enumerate(criteria):
        if not isinstance(c, dict):
            problems.append(f"criterion #{i + 1} is not an object.")
            continue
        cid = str(c.get("id") or c.get("title") or f"#{i + 1}")
        kind = str(c.get("kind", "")).strip().lower()
        verdict = str(c.get("verdict", "")).strip().lower()

        if kind not in ("behavioral", "parity", "data-entry", "transient"):
            problems.append(
                f"{cid}: missing/invalid `kind` (expected behavioral|parity|data-entry|transient)."
            )
        if verdict not in ("pass", "fail"):
            problems.append(f"{cid}: missing/invalid `verdict` (expected Pass|Fail).")

        # A Pass-overall cannot coexist with a failing criterion.
        if verdict == "fail":
            problems.append(
                f"{cid}: verdict is Fail — QA cannot pass overall while this AC fails."
            )
            continue
        if verdict != "pass":
            continue  # already flagged above

        # Pass criterion must cite real evidence.
        evidence = c.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        real = [e for e in evidence if evidence_exists(e, root, spec_dir)]
        if not real:
            problems.append(
                f"{cid}: marked Pass but cites no evidence file that exists on disk "
                f"(evidence={evidence!r})."
            )

        if kind == "parity":
            checklist = c.get("checklist")
            if not isinstance(checklist, list) or not checklist:
                problems.append(
                    f"{cid}: parity criterion has no per-element `checklist` — a parity Pass must "
                    f"enumerate every old-side element/state (label, ✔/underline state indicator, "
                    f"selection styling, control group, layout, values) and confirm each."
                )
            else:
                for j, row in enumerate(checklist):
                    if not isinstance(row, dict):
                        problems.append(
                            f"{cid}: checklist row #{j + 1} is not an object."
                        )
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
                    if not evidence_exists(row.get("evidence", ""), root, spec_dir):
                        problems.append(
                            f"{cid}: checklist element '{row.get('element', '?')}' cites no existing "
                            f"evidence file."
                        )

        if kind == "data-entry":
            p = c.get("persistence")
            if not isinstance(p, dict):
                problems.append(
                    f"{cid}: data-entry criterion has no `persistence` proof — a Pass must show "
                    f"fill→save→reload (before/after/reload, persisted, no bleed) with evidence."
                )
            else:
                if p.get("persisted") is not True:
                    problems.append(
                        f"{cid}: persistence.persisted is not true — the saved value was not "
                        f"confirmed to survive reload."
                    )
                if p.get("bled_to_others") is True:
                    problems.append(
                        f"{cid}: persistence.bled_to_others is true — Save wrote fields it should not."
                    )
                if not evidence_exists(p.get("evidence", ""), root, spec_dir):
                    problems.append(
                        f"{cid}: persistence proof cites no existing evidence file."
                    )

        if kind == "transient":
            t = c.get("transient")
            if not isinstance(t, dict):
                problems.append(
                    f"{cid}: transient criterion has no `transient` proof — a Pass must show the "
                    f"feedback (save flash/toast, inline validation, optimistic UI) APPEARED then "
                    f"DISAPPEARED, with a capture taken inside the transient window."
                )
            else:
                if t.get("appeared") is not True:
                    problems.append(
                        f"{cid}: transient.appeared is not true — the feedback was never observed "
                        f"to appear after its trigger."
                    )
                if t.get("disappeared") is not True:
                    problems.append(
                        f"{cid}: transient.disappeared is not true — the appear-then-disappear "
                        f"behavior was not confirmed (steady-state feedback is parity/behavioral, "
                        f"not transient)."
                    )
                if not evidence_exists(t.get("mid_window_capture", ""), root, spec_dir):
                    problems.append(
                        f"{cid}: transient criterion must cite a `mid_window_capture` taken while "
                        f"the feedback was visible — a settled after-the-fact frame cannot prove a "
                        f"transient (no existing mid-window capture file referenced)."
                    )

    vet_notes: list[str] = []
    visual_fidelity = data.get("visual_fidelity") if isinstance(data, dict) else None
    if isinstance(visual_fidelity, list):
        for i, entry in enumerate(visual_fidelity):
            if not isinstance(entry, dict):
                problems.append(f"visual_fidelity #{i + 1} is not an object.")
                continue
            state = str(entry.get("state") or f"#{i + 1}")
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
            except Exception as exc:  # noqa: BLE001 - any parse error fails the gate
                problems.append(
                    f"visual_fidelity[{state}]: report file is not valid JSON ({exc})."
                )
                continue

            summary = report.get("summary") if isinstance(report, dict) else None
            if not isinstance(summary, dict):
                problems.append(
                    f"visual_fidelity[{state}]: report has no `summary` object."
                )
                continue

            missing_count = summary.get("missingCount", 0)
            if missing_count:
                missing = report.get("missing") or []
                selectors = [
                    str(m.get("selector", "?")) for m in missing if isinstance(m, dict)
                ]
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

    # Run-id coherence (opt-in: enforced only when the QA pass stamped a runId).
    # Replaces mtime forensics: each Pass criterion must cite at least one artifact
    # produced by THIS run (listed in qa/run-manifest.json under the same runId);
    # additional reference evidence (old-side archives, accepted-divergence records)
    # may be older and is not required to appear in the manifest.
    run_id = str(data.get("runId", "")).strip()
    if not run_id:
        problems.append("qa-evidence.json has no runner-produced runId.")
    else:
        manifest_artifacts: list[str] = []
        if manifest:
            manifest_run_id = str(
                manifest.get("runId") or manifest.get("run_id") or ""
            ).strip()
            if manifest_run_id != run_id:
                problems.append(
                    f"run-manifest runId '{manifest_run_id}' does not match "
                    f"qa-evidence runId '{run_id}' — the evidence and summary must come "
                    f"from the same execution."
                )
            manifest_artifacts = [
                str(a.get("path") or a.get("file") or "").strip()
                if isinstance(a, dict)
                else str(a).strip()
                for a in manifest.get("artifacts") or []
            ]
            basenames = {os.path.basename(a) for a in manifest_artifacts if a}
            for c in criteria:
                if (
                    not isinstance(c, dict)
                    or str(c.get("verdict", "")).strip().lower() != "pass"
                ):
                    continue
                cid = str(c.get("id") or c.get("title") or "?")
                evidence = c.get("evidence") or []
                if isinstance(evidence, str):
                    evidence = [evidence]
                if not any(
                    os.path.basename(str(e).strip()) in basenames for e in evidence
                ):
                    problems.append(
                        f"{cid}: no cited evidence file appears in this run's manifest "
                        f"(runId {run_id}) — every Pass criterion must cite at least one "
                        f"artifact produced by the current execution."
                    )

    if problems:
        logger.warning("QA evidence gate invalidated this pass — %d problem(s)", len(problems))
        emit(
            "invalid",
            "QA evidence gate invalidated this pass — the machine-checkable proof is missing or "
            "self-contradictory. Fix and re-QA:\n- " + "\n- ".join(problems),
        )

    n = len(criteria)
    note = f"QA evidence gate: {n} criteria validated (evidence files present, parity checklists "
    note += "enumerated, save-flows proven). "
    if vet_notes:
        note += "visual_fidelity: " + "; ".join(vet_notes) + ". "
    note += claimed_notes or ""
    logger.info("QA evidence gate passed: %d criteria validated", n)
    emit("passed", note.strip())


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("verify_qa_evidence"))
