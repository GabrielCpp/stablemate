"""Controlled semantic behavior review versus doctor, plus frozen stablemate book slices."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from _behavior_eval import (
    Adjudication, Case, GroundTruth, RepairedSlice, Slice, adjudicate, bind_truth, exact_score, file_hashes, freeze_slice,
    prepare, repaired_truth, usage, variant_book, write_json,
)
from _stablemate import stablemate_checkout, uv_run
from groom import store
from ostler.api import Ostler
from ostler.behavior import AuditPreparation, AuditReport, validate_verdicts
from paddock import Run, Score, step, task
from pydantic import BaseModel, Field, TypeAdapter
from workhorse.manifest import ContextManifest

task(name="okf-behavior-audit", seed="okf-behavior", config="configs/okf-behavior.toml")


class Trial(BaseModel):
    id: str
    source: str
    context_paths: tuple[str, ...] = ()
    service: str
    expected: dict[str, set[str]]
    before: dict[str, str]
    packets: int
    candidates: int
    claims: int
    preparation_seconds: float


class Outcome(BaseModel):
    id: str
    returncode: int
    seconds: float
    unchanged: bool
    report: str
    model_turns: int
    telemetry: dict[str, object] = Field(default_factory=dict)


class Review(BaseModel):
    status: str
    reports: list[AuditReport] = Field(default_factory=list)
    omitted_packets: int = 0


def trial_root(run: Run) -> Path:
    return run.stage / "artifacts" / "cases"


@step()
def freeze_inputs(run: Run) -> None:
    replay = run.param("replay_stage")
    book_state = run.param("book_state", "baseline")
    language = run.param("language", "python")
    if language not in {"python", "go"}:
        raise ValueError("language must be python or go")
    if language == "go" and (replay or book_state != "baseline" or run.param_bool("support_context", False)):
        raise ValueError("language=go requires fresh controlled baseline cases without support_context")
    if book_state not in {"baseline", "repaired"}:
        raise ValueError("book_state must be baseline or repaired")
    if replay and book_state == "repaired":
        raise ValueError("book_state=repaired requires current books, not replay_stage")
    if replay:
        original = Path(replay).resolve()
        if not (original / "score.json").is_file():
            raise ValueError("replay_stage must name a previously scored stage")
        shutil.copytree(original / "artifacts/cases", trial_root(run))
        if wanted := set(run.param_list("cases")):
            replay_trials = TypeAdapter(list[Trial]).validate_json((trial_root(run) / "trials.json").read_text())
            if wanted - {item.id for item in replay_trials}:
                raise ValueError("replay names cases absent from the original stage")
            write_json(trial_root(run) / "trials.json", [item.model_dump(mode="json") for item in replay_trials if item.id in wanted])
        write_json(trial_root(run) / "replay.json", {"source_stage": str(original), "new_model_turns": 0,
                                                    "original_steps": json.loads((original / "steps.json").read_text())})
        return
    checkout = stablemate_checkout(run)
    fixture = run.data_dir / ("fixtures/okf-behavior-go" if language == "go" else "fixtures/okf-behavior")
    truth = GroundTruth.model_validate_json((fixture / "ground-truth.json").read_text())
    slices = [] if language == "go" else TypeAdapter(list[Slice]).validate_json((fixture / "stablemate-slices.json").read_text())
    wanted = set(run.param_list("cases")) or {case.id for case in truth.cases} | {item.id for item in slices}
    unknown = wanted - {case.id for case in truth.cases} - {item.id for item in slices}
    if unknown:
        raise ValueError(f"unknown cases: {sorted(unknown)}")
    repairs: dict[str, RepairedSlice] = {}
    if book_state == "repaired":
        repairs = {item.id: item for item in TypeAdapter(list[RepairedSlice]).validate_json(
            (fixture / "repaired-slices.json").read_text())}
        if wanted - repairs.keys():
            raise ValueError("book_state=repaired requires explicitly declared Stablemate cases")
    trials: list[Trial] = []
    support_context = run.param_bool("support_context", False)
    for case in [*truth.cases, *[Case(id=item.id, defects=item.defects) for item in slices]]:
        if case.id not in wanted:
            continue
        directory = trial_root(run) / case.id
        witness = directory / "witness"
        directory.mkdir(parents=True, exist_ok=True)
        context_paths: tuple[str, ...] = ()
        if case.id.startswith("stablemate-"):
            selection = next(item for item in slices if item.id == case.id)
            if book_state == "repaired":
                case = repaired_truth(checkout, selection, repairs[case.id])
            metadata = freeze_slice(checkout, witness, selection)
            if book_state == "repaired":
                case = repaired_truth(witness, selection, repairs[case.id])
                write_json(directory / "repair.json", repairs[case.id].model_dump(mode="json"))
            write_json(directory / "scope.json", metadata)
            source, service = selection.source, selection.service
            if support_context:
                context_paths = tuple(selection.context)
        else:
            shutil.copytree(run.repo, witness)
            source, service = "service.py", "dispatch"
            if language == "go":
                (witness / "service.py").unlink()
                shutil.copytree(fixture / "source", witness, dirs_exist_ok=True)
                source = "service.go"
            book = witness / "docs/features/dispatch/dispatch.md"
            book.write_text(variant_book(book.read_text(), case.id), encoding="utf-8")
        started = time.monotonic()
        prepared = prepare(witness, source, context_paths=context_paths)
        if language == "go" and not prepared.inventory.candidates:
            raise ValueError("Go extraction unavailable: selected service.go produced no candidates")
        aliases = bind_truth(case, prepared)
        elapsed = time.monotonic() - started
        if len(prepared.packets) != 1:
            raise ValueError(f"{case.id}: expected one bounded packet, got {len(prepared.packets)}")
        write_json(directory / "preparation.json", prepared.model_dump(mode="json"))
        write_json(directory / "ground-truth.json", case.model_dump(mode="json"))
        trials.append(Trial(id=case.id, source=source, service=service, expected=aliases,
                            context_paths=context_paths,
                            before=file_hashes(witness), packets=len(prepared.packets),
                            candidates=prepared.selected_candidates, claims=prepared.selected_claims,
                            preparation_seconds=elapsed))
    write_json(trial_root(run) / "trials.json", [trial.model_dump(mode="json") for trial in trials])
    audit = checkout / "workflows/src/workhorse_workflows/okf_builder/audit"
    write_json(trial_root(run) / "toolchain.json", {
        "unpinned": run.pinned is None or not run.pinned.pinned,
        "support_context": support_context,
        "book_state": book_state,
        "language": language,
        "audit_flow_hashes": file_hashes(audit) if audit.exists() else {},
        "behavior_hashes": {name: file_hashes(checkout / "ostler/ostler").get(name)
                            for name in ("behavior.py", "behavior_models.py", "behavior_python.py", "behavior_go.py")},
        "model_config": run.config.read_text(),
        "scope_note": "Current working-tree slices, not HEAD. Originals never edited. No whole-book conclusion.",
    })


@step()
def deterministic_baseline(run: Run) -> None:
    if run.param("replay_stage"):
        return
    trials = TypeAdapter(list[Trial]).validate_json((trial_root(run) / "trials.json").read_text())
    for trial in trials:
        witness = trial_root(run) / trial.id / "witness"
        started = time.monotonic()
        report = Ostler(witness).doctor().data
        write_json(trial_root(run) / trial.id / "doctor.json", {
            "seconds": time.monotonic() - started, "report": report,
            "note": "Structural and citation findings only; not semantic detection credit.",
        })
        if file_hashes(witness) != trial.before:
            raise ValueError(f"{trial.id}: doctor changed its witness")


@step()
def semantic_review(run: Run) -> None:
    if run.param("replay_stage"):
        return
    checkout = stablemate_checkout(run)
    trials = TypeAdapter(list[Trial]).validate_json((trial_root(run) / "trials.json").read_text())
    outcomes: list[Outcome] = []
    # Six packets normally mean six turns. Reserve two attempts per next packet and
    # stop before exceeding ten, rather than silently buying another repair ladder.
    turns = 0
    ceiling = 6 if run.param("language", "python") == "go" else 10
    maximum = int(run.param("max_turns", str(ceiling)))
    if not 1 <= maximum <= ceiling:
        raise ValueError(f"max_turns must be between 1 and {ceiling}")
    for trial in trials:
        if turns + 2 > maximum:
            break
        directory = trial_root(run) / trial.id
        witness = directory / "witness"
        context = directory / "context.json"
        context.write_text(ContextManifest().model_dump_json(), encoding="utf-8")
        runs = directory / "runs"
        run_id = f"behavior-{run.label}-{trial.id}"
        started = time.monotonic()
        result = run.cli(
            *uv_run(checkout, "workhorse-workflows"), "workhorse-okf-builder", "run", "audit",
            "--runs-dir", str(runs), "--run-id", run_id,
            "--context-file", str(context), "--config", str(run.config),
            "--params", json.dumps({"docs_path": str(witness), "source_path": trial.source,
                                      "context_paths": trial.context_paths,
                                     "service": trial.service, "max_packets": 1}),
            cwd=witness, timeout=700, log_name=trial.id,
        )
        elapsed = time.monotonic() - started
        reports = list(runs.glob("*/behavior-audit.json"))
        report = str(reports[0].relative_to(run.stage)) if len(reports) == 1 else ""
        attempts = len(list(runs.glob("*/behavior-audit/*/raw-*.json")))
        # Failed model invocations need not produce a raw receipt. The per-turn
        # engine artifacts are the cost denominator when they exist.
        turn_files = list(runs.glob("*/turns/*/prompt.md"))
        attempts = max(attempts, len(turn_files))
        turns += max(1, attempts)
        outcomes.append(Outcome(id=trial.id, returncode=result.returncode, seconds=elapsed,
                                unchanged=file_hashes(witness) == trial.before, report=report,
                                model_turns=attempts, telemetry=store.run_profile(run_id) or {}))
        write_json(trial_root(run) / "outcomes.json", [item.model_dump(mode="json") for item in outcomes])
        if not outcomes[-1].unchanged:
            raise ValueError(f"{trial.id}: read-only audit mutated the witness")
        if result.returncode != 0:
            break


def score(run: Run) -> Score:
    trials = TypeAdapter(list[Trial]).validate_json((trial_root(run) / "trials.json").read_text())
    outcome_path = trial_root(run) / "outcomes.json"
    outcomes = {item.id: item for item in TypeAdapter(list[Outcome]).validate_json(outcome_path.read_text())} if outcome_path.exists() else {}
    rows: list[dict[str, object]] = []
    adjudications: dict[str, Adjudication] = {}
    if name := run.param("adjudication"):
        adjudications = TypeAdapter(dict[str, Adjudication]).validate_json(
            (run.data_dir / "fixtures/okf-behavior/adjudications" / name).read_text())
    for trial in trials:
        directory = trial_root(run) / trial.id
        outcome = outcomes.get(trial.id)
        row: dict[str, object] = {"case": trial.id, "preparation": trial.model_dump(mode="json")}
        rows.append(row)
        doctor = directory / "doctor.json"
        row["doctor"] = json.loads(doctor.read_text()) if doctor.exists() else None
        if outcome is None or not outcome.report or not outcome.unchanged or outcome.returncode != 0:
            row["status"] = "inconclusive"
            continue
        row["execution"] = outcome.model_dump(mode="json")
        row["usage"] = usage(directory / "runs")
        prepared = AuditPreparation.model_validate_json((directory / "preparation.json").read_text())
        # Rebuild from this trial's sealed source, never from the original fixture.
        if prepare(directory / "witness", trial.source, context_paths=trial.context_paths) != prepared:
            raise ValueError(f"{trial.id}: stale prepared evidence")
        review = Review.model_validate_json((run.stage / outcome.report).read_text())
        packets = {packet.digest: packet for packet in prepared.packets}
        adverse: set[str] = set()
        unresolved: set[str] = set()
        seen: set[str] = set()
        for report in review.reports:
            packet = packets[report.packet_digest]
            validate_verdicts(packet, report.verdicts)
            if packet.digest in seen:
                raise ValueError(f"{trial.id}: duplicate receipt")
            seen.add(packet.digest)
            adverse.update(item.id for item in report.verdicts.claims if item.status in {"partial", "contradicted"})
            adverse.update(item.id for item in report.verdicts.candidates if item.status == "missing")
            unresolved.update(item.id for item in (*report.verdicts.claims, *report.verdicts.candidates)
                              if item.status == "unresolved")
        if seen != set(packets) or review.omitted_packets:
            row["status"] = "inconclusive"
            continue
        row.update(exact_score(trial.expected, adverse))
        row["status"] = "reviewed"
        row["unresolved"] = sorted(unresolved)
        row["adverse"] = sorted(adverse)
        row["claim_contradictions"] = sorted(item.id for report in review.reports
                                             for item in report.verdicts.claims if item.status == "contradicted")
        row["partial_claims"] = sorted(item.id for report in review.reports
                                       for item in report.verdicts.claims if item.status == "partial")
        row["unmatched_policy"] = "Potential false positives; adjudicate explanations against frozen source before claiming quality."
        if trial.id in adjudications:
            aliases = {target for targets in trial.expected.values() for target in targets}
            row["adjudication"] = adjudicate(adjudications[trial.id], prepared.packets[0].digest, adverse - aliases)
    reviewed = sum(row["status"] == "reviewed" for row in rows)
    detail = tuple(f"  {row['case']}: caught={row.get('caught', 'unknown')} missed={row.get('missed', 'unknown')} "
                   f"unmatched={len(value) if isinstance(value := row.get('unmatched_adverse'), list) else 'unknown'}"
                   for row in rows)
    return Score(headline=f"behavior audit: {reviewed}/{len(rows)} cases reviewed; exact-ID results in score.json",
                 detail=detail, data={"cases": rows}, caveats=(
                     "Uncommitted toolchain measured with --no-pin-project; not a released baseline.",
                     "Single model sample per case; packet-only AST context, no execution or whole-book claim.",
                     "Stablemate slices omit surrounding claim groups; unmatched findings require adjudication.",
                 ))
