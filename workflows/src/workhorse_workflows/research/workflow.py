"""The `research` gate loop as a state machine."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, ClassVar

from workhorse.cli import console_script
from workhorse.pyflow import Await, Continue, Done, Registry, Workflow
from workhorse_workflows.coder.shared.blueprint import blueprint as gate_blueprint
from workhorse_workflows.coder.shared.dev import GATE_ORDER, run_gate
from workhorse_workflows.kit import commit_paths, set_identity
from workhorse_workflows.research.nodes import (
    append_history,
    blueprint,
    build_dossier,
    check_envelope,
    clone_repo,
    collect_job,
    dry_run,
    job_dir_for,
    kill_job,
    load_program,
    publish_results,
    record_spend,
    submit_job,
    watch_job,
)
from workhorse_workflows.research.nodes.dossier import (
    parse_frozen_target,
    render_dossier,
    resolvability,
    summarize,
)
from workhorse_workflows.research.schemas import (
    Budget,
    Build,
    CodeReview,
    Collected,
    Design,
    Dossier,
    ExtendResult,
    FailedCriterion,
    FrozenTarget,
    GateCheck,
    GateSelection,
    GoalReview,
    LeadReview,
    NewDirectionResult,
    NewTarget,
    Program,
    ProgramReview,
    RecharterResult,
    RecordResult,
    ReviveResult,
    TriageResult,
)


MAX_BUILD_FIXES = 3
MAX_REWORKS = 2
MAX_RESCOPES = 2
MAX_LEAD_REVIEWS = 4
MAX_EXTENSIONS = 6
MAX_PROGRAM_REVIEWS = 8
MAX_RECHARTERS = 2
MAX_RECHARTER_FIXES = 1
PROGRAM_REVIEW_EVERY = 3

GATE_TEMPLATE = Path(__file__).resolve().parent / "scaffold" / "templates" / "gate.md"

BLOCKED_NAME = "BLOCKED.md"

OPERATOR_RELEASED = "an operator addressed"

GOAL_REACHED = "GOAL_REACHED"
GOAL_IMPOSSIBLE = "GOAL_IMPOSSIBLE"
GOAL_BANKED = "GOAL_BANKED"

GOAL_STATUS = {
    GOAL_REACHED: "reached",
    GOAL_IMPOSSIBLE: "impossible",
    GOAL_BANKED: "banked",
}

GOAL = "GOAL"


class Research(Workflow):
    """One gate-loop engine, driving any research program."""

    max_transitions: ClassVar[int] = 3000

    program: str = ""

    repo_url: str = ""

    repo_branch: str = "main"

    launch_dir: str = ""

    reauthorize: bool = False

    def setup(self) -> Program:
        """Get a checkout, then read the program manifest out of it."""
        repo = self.call(
            clone_repo,
            repo_dir=self.repo_dir,
            repo_url=self.repo_url,
            repo_branch=self.repo_branch,
        )
        return self.call(
            load_program,
            self.program,
            repo.repo_dir,
            self.launch_dir,
            reauthorize=self.reauthorize,
        )

    def labels(self) -> dict[str, str]:
        """What the run is working on — telemetry the engine cannot know."""
        return {"program": self.ctx.program_dir}


    def _program_args(self, **extra: Any) -> dict[str, Any]:
        """The program triple a prompt opens with, plus this call's own arguments."""
        return {
            "repo_dir": self.ctx.repo_dir,
            "program_dir": self.ctx.program_dir,
            "progress_path": self.ctx.progress_path,
            **extra,
        }

    def _abs(self, rel: str) -> Path:
        """A repo-relative path as the absolute one an operator gate needs."""
        return Path(self.ctx.repo_dir) / rel

    def _blocked(self, questions: str, resume: Any, /, **params: Any) -> Await:
        """Park on the operator gate, naming the state to re-enter with what."""
        return Await(
            self._abs(f"{self.ctx.program_dir}/{BLOCKED_NAME}"), questions, resume, **params
        )

    def _released_by(self, fix_reason: str) -> str:
        """`fix_reason`, plus the gate itself when an operator is what released the state."""
        if not fix_reason.startswith(OPERATOR_RELEASED):
            return fix_reason
        gate = self._abs(f"{self.ctx.program_dir}/{BLOCKED_NAME}")
        if not gate.is_file():
            return fix_reason
        return (
            f"{fix_reason}\n\n"
            f"The operator answered on `{self.ctx.program_dir}/{BLOCKED_NAME}`, below, "
            "oldest first: your own asks and the answers to them. Do what the answers "
            "say. Where one tells you a fault is not yours and needs no change here, it "
            "is settled — do not raise it again; carry on with the work it releases you "
            "to do. The `STATUS:` header is the engine's bookkeeping, not yours.\n\n"
            f"{gate.read_text(encoding='utf-8').strip()}"
        )

    def _publish(self, summary: str) -> None:
        """Commit what the last turn wrote onto the result branch."""
        self.call(
            publish_results,
            self.ctx.repo_dir,
            self.ctx.result_branch,
            self.ctx.program_dir,
            summary=summary,
        )

    def _spent(self, budget: Budget) -> tuple[int, int]:
        """`(extensions, lead_reviews)` this **program** has spent, not this run."""
        return (
            self.ctx.extensions_spent + budget.extensions,
            self.ctx.lead_reviews_spent + budget.lead_reviews,
        )

    def _program_spent(self, budget: Budget) -> tuple[int, int]:
        """`(program_reviews, recharters)` this **program** has spent, not this run."""
        return (
            self.ctx.program_reviews_spent + budget.program_reviews,
            self.ctx.recharters_spent + budget.recharters,
        )

    def _persist(self, budget: Budget, *, status: str = "active") -> None:
        """Write the program's spend to its ledger, before the publish that commits it."""
        extensions, lead_reviews = self._spent(budget)
        program_reviews, recharters = self._program_spent(budget)
        self.call(
            record_spend,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            extensions=extensions,
            lead_reviews=lead_reviews,
            status=status,
            program_reviews=program_reviews,
            recharters=recharters,
        )

    def _dossier(self, budget: Budget) -> Dossier:
        """The program's computed evidence — numbers, dates, counts — with no model in it."""
        _, lead_reviews = self._spent(budget)
        program_reviews, _ = self._program_spent(budget)
        return self.call(
            build_dossier,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            progress_path=self.ctx.progress_path,
            code_root=self.ctx.code_root,
            lead_reviews=lead_reviews,
            program_reviews=program_reviews,
            gate_cycles=budget.gate_cycles,
            review_every=PROGRAM_REVIEW_EVERY,
        )

    def _history(
        self, event: str, gate_id: str = "", *, note: str = "", fingerprint: str = ""
    ) -> None:
        """One line into the program's `history.jsonl` — the record the dossier counts."""
        self.call(
            append_history,
            repo_dir=self.ctx.repo_dir,
            program_dir=self.ctx.program_dir,
            event=event,
            gate_id=gate_id,
            note=note,
            fingerprint=fingerprint,
        )

    def _check_target(self, target: NewTarget | None = None) -> str:
        """The in-code resolvability check on a (re)written frozen target."""
        if target is not None and target.n:
            frozen = FrozenTarget(
                metric=target.metric,
                dataset=target.dataset,
                threshold=target.threshold,
                threshold_count=target.threshold_count,
                n=target.n,
                threshold_value=target.threshold_count / target.n,
                seeds=target.seeds,
                deadline=target.deadline,
                baseline_count=target.baseline_count,
                baseline_value=target.baseline_count / target.n,
            )
        else:
            readme = self._abs(f"{self.ctx.program_dir}/README.md")
            text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
            frozen = parse_frozen_target(text)
            if not frozen.n:
                return (
                    "no `Frozen target` table with a `count/n` threshold could be read "
                    f"from {self.ctx.program_dir}/README.md"
                )
        verdict = resolvability(frozen)
        return "" if verdict.resolvable else verdict.statement

    def _record(self, gate_id: str, *, forced: str = "") -> RecordResult:
        """Write one outcome to the program's progress file."""
        args = self._program_args(gate_id=gate_id)
        if forced:
            args["gate_doc_path"] = f"{self.ctx.program_dir}/README.md"
            args["forced_outcome"] = forced
        return self.agent(
            "prompts/record-result.md",
            returns=RecordResult,
            power="max" if forced else "low",
            args=args,
        )

    def _to_lead(
        self,
        gate_id: str,
        gate_doc_path: str,
        *,
        escalation: str,
        notes: str,
        budget: Budget,
        failed_criteria: list[FailedCriterion] | None = None,
    ) -> Continue:
        """Hand an exhausted repair budget to the lead, as a gate-level question."""
        return Continue(
            None,
            self.program_review,
            origin="escalation",
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            budget=budget,
        )

    def _job_dir(self, gate_id: str, suffix: str = "") -> str:
        return job_dir_for(self.ctx.repo_dir, self.ctx.program_dir, gate_id, suffix)


    def start(self, budget: Budget = Budget()) -> Continue:
        """Pick the next gate, and route on what came back."""
        dossier = self._dossier(budget)
        selection = self.agent(
            "prompts/select-next-gate.md",
            returns=GateSelection,
            power="low",
            args=self._program_args(dossier_summary=summarize(dossier)),
        )
        if selection.gate_id in ("", "none"):
            return Continue(selection, self.goal_review, budget=budget)
        if selection.program_killed:
            return Continue(
                selection,
                self.program_review,
                origin="kill",
                gate_id=selection.gate_id,
                gate_doc_path=selection.gate_doc_path,
                failed_criteria=[],
                notes=selection.rationale,
                escalation="",
                budget=budget,
            )
        if dossier.review_due:
            return Continue(
                selection,
                self.program_review,
                origin="periodic",
                gate_id=selection.gate_id,
                gate_doc_path=selection.gate_doc_path,
                failed_criteria=[],
                notes=selection.rationale,
                escalation="",
                budget=budget,
            )
        self._history("gate_selected", selection.gate_id)
        return Continue(
            selection,
            self.design,
            gate_id=selection.gate_id,
            gate_doc_path=selection.gate_doc_path,
            budget=budget.fresh_gate(),
        )


    def design(
        self,
        gate_id: str,
        gate_doc_path: str,
        budget: Budget = Budget(),
        rework_notes: str = "",
        failed_criteria: list[FailedCriterion] | None = None,
        rescope_reason: str = "",
    ) -> Continue:
        """Write the protocol, declare what it will cost, and time a calibration probe."""
        if rework_notes:
            self._history("rework", gate_id, note=rework_notes)
        elif rescope_reason:
            self._history("rescope", gate_id, note=rescope_reason)
        design = self.agent(
            "prompts/design-experiment.md",
            returns=Design,
            power="max",
            args=self._program_args(
                code_root=self.ctx.code_root,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rework_notes=rework_notes,
                failed_criteria=[c.model_dump(mode="json") for c in (failed_criteria or [])],
                rescope_reason=rescope_reason,
                rework_count=budget.reworks,
                rescope_count=budget.rescopes,
                envelope_ram_gb=self.ctx.envelope_ram_gb,
                envelope_cpus=self.ctx.envelope_cpus,
                envelope_gpu=self.ctx.envelope_gpu,
                envelope_disk_gb=self.ctx.envelope_disk_gb,
            ),
        )
        if design.status == "blocked":
            self._history("design_blocked", gate_id, note=design.notes)
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="design_blocked",
                notes=design.notes or "the scientist reported the design blocked, without a reason",
                budget=budget,
            )
        envelope = self.call(
            check_envelope,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
            gpu=design.gpu,
            disk_gb=design.disk_gb,
            envelope_ram_gb=self.ctx.envelope_ram_gb,
            envelope_cpus=self.ctx.envelope_cpus,
            envelope_gpu=self.ctx.envelope_gpu,
            envelope_disk_gb=self.ctx.envelope_disk_gb,
        )
        if not envelope.fits:
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=(
                        f"{MAX_RESCOPES} rescopes did not fit this gate onto the "
                        f"declared machine. Last attempt: {envelope.reason}"
                    ),
                    budget=budget,
                )
            return Continue(
                design,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=envelope.reason,
                budget=budget.rescoped(),
            )
        return Continue(
            design,
            self.build,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            budget=budget,
        )


    def build(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        budget: Budget = Budget(),
        fix_reason: str = "",
    ) -> Continue | Await:
        """Make the protocol runnable, then rehearse it at `n=1` through the runner."""
        if fix_reason:
            self._history("build_fix", gate_id, note=fix_reason)
        build = self.agent(
            "prompts/build-experiment.md",
            returns=Build,
            power="high",
            args=self._program_args(
                code_root=self.ctx.code_root,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                fix_reason=self._released_by(fix_reason),
                fix_count=budget.build_fixes,
                result_file="result.json",
            ),
        )
        if build.fault_locus == "tooling":
            return self._blocked(
                self._tooling_question(
                    gate_id,
                    component=build.component,
                    detail=build.notes,
                    where="building the experiment",
                ),
                self.build,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                budget=budget,
                fix_reason=f"{OPERATOR_RELEASED}: {build.notes}",
            )
        if build.status == "blocked":
            self._history("build_blocked", gate_id, note=build.notes)
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="build_blocked",
                notes=build.notes or "the engineer reported the build blocked, without a reason",
                budget=budget,
            )
        if not build.command:
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus="repo",
                component="",
                reason="the build produced no command",
                detail=build.notes,
                where="the build",
            )
        gate_outcome = None
        for check in GATE_ORDER:
            gate_outcome = self.call(
                run_gate,
                build.cwd or self.ctx.repo_dir,
                "",
                check,
                repo_dir=self.ctx.repo_dir,
            )
            if gate_outcome.status == "dirty":
                break
        if gate_outcome is not None and gate_outcome.status == "dirty":
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus="repo",
                component="",
                reason=f"the {gate_outcome.gate} gate failed: {gate_outcome.reason}",
                detail=gate_outcome.output,
                where=f"the {gate_outcome.gate} gate",
            )
        review = self.agent(
            "prompts/code-review-experiment.md",
            returns=CodeReview,
            power="medium",
            args=self._program_args(
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                build=build.model_dump(mode="json"),
            ),
        )
        if review.status != "approve":
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus="repo",
                component="",
                reason=f"code review: {review.findings}",
                detail=review.notes,
                where="the code review",
            )
        set_identity(self.ctx.repo_dir, "Research Agent", "research-agent@local")
        commit_paths(
            build.cwd or self.ctx.repo_dir,
            f"feat({gate_id.lower()}): build experiment",
            *build.code_files,
        )
        rehearsal = self.call(
            dry_run,
            job_dir=self._job_dir(gate_id, suffix="-dry"),
            command=build.dry_run_command,
            cwd=build.cwd or self.ctx.repo_dir,
            repo_dir=self.ctx.repo_dir,
            result_file=build.result_file,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
        )
        if not rehearsal.ok:
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus=rehearsal.fault_locus,
                component="",
                reason=f"the n=1 rehearsal failed: {rehearsal.reason}",
                detail=rehearsal.stderr_tail,
                where="the n=1 rehearsal",
            )
        return Continue(
            build,
            self.submit,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            build=build,
            budget=budget,
        )

    def _tooling_question(
        self, gate_id: str, *, component: str, detail: str, where: str
    ) -> str:
        """The ask an operator answers when the fault is not in the repo."""
        named = component or "unnamed — the fault was classified from the traceback"
        return (
            f"Gate {gate_id or GOAL} is blocked on a **tooling** fault in {where}.\n\n"
            f"Component: {named}\n\n"
            f"{detail or '(no detail was reported)'}\n\n"
            "Fix the component, then answer this gate. The run resumes by rebuilding "
            "the experiment; nothing about the protocol or the gate's thresholds has "
            "changed, and no science budget was spent on this."
        )

    def _repair(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        budget: Budget,
        *,
        locus: str,
        component: str,
        reason: str,
        detail: str,
        where: str,
    ) -> Continue | Await:
        """Route one "produced no measurement" failure by **fault locus**."""
        if locus == "tooling":
            return self._blocked(
                self._tooling_question(
                    gate_id, component=component, detail=detail or reason, where=where
                ),
                self.build,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design.model_dump(mode="json"),
                budget=budget,
                fix_reason=f"{OPERATOR_RELEASED} a tooling fault: {reason}",
            )
        if budget.build_fixes >= MAX_BUILD_FIXES:
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="max_build_fixes",
                notes=(
                    f"{MAX_BUILD_FIXES} engineering repairs did not get this gate to a "
                    f"measurement. Last failure: {reason}"
                ),
                budget=budget,
            )
        return Continue(
            None,
            self.build,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            design=design,
            budget=budget.built(),
            fix_reason=f"{reason}\n\n{detail}".strip(),
        )


    def submit(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Launch the measurement detached, and route the three ways it can refuse."""
        job = self.call(
            submit_job,
            job_dir=self._job_dir(gate_id),
            command=build.command,
            cwd=build.cwd or self.ctx.repo_dir,
            memory_mb=design.memory_mb,
            cpus=design.cpus,
            estimate_s=design.estimate_s,
            result_file=build.result_file,
            min_containment=self.ctx.min_containment,
            labels={"gate": gate_id, "program": self.ctx.program_dir},
            probe_units_timed=design.probe.units_timed,
        )
        if job.submitted:
            return Continue(
                job,
                self.await_result,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design,
                build=build,
                job_dir=job.job_dir,
                budget=budget,
            )
        if job.fault_locus == "design":
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=f"the design kept arriving without a probe: {job.error}",
                    budget=budget,
                )
            return Continue(
                job,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=job.error,
                budget=budget.rescoped(),
            )
        return self._repair(
            gate_id,
            gate_doc_path,
            design,
            budget,
            locus=job.fault_locus,
            component="workhorse.job" if job.fault_locus == "tooling" else "",
            reason=f"the job would not launch: {job.error}",
            detail="",
            where="submitting the job",
        )

    def await_result(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        budget: Budget = Budget(),
        seen_multiple: float = 0.0,
    ) -> Continue | Await:
        """Wait for the measurement — for hours or days, across driver deaths."""
        watch = self.call(watch_job, job_dir=job_dir, seen_multiple=seen_multiple)
        common = {
            "gate_id": gate_id,
            "gate_doc_path": gate_doc_path,
            "design": design.model_dump(mode="json"),
            "build": build.model_dump(mode="json"),
            "job_dir": job_dir,
            "budget": budget,
        }
        if watch.action == "collect":
            return Continue(watch, self.collect, **common)
        if watch.action == "triage":
            return Continue(
                watch, self.triage, overrun_multiple=watch.overrun_multiple, **common
            )
        return Await.on_machine(
            Path(watch.wake_path),
            "",
            self.await_result,
            seen_multiple=seen_multiple,
            **common,
        )

    def triage(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        overrun_multiple: float = 0.0,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """The engineer, mid-flight, on a job running far past its estimate."""
        verdict = self.agent(
            "prompts/triage-overrun.md",
            returns=TriageResult,
            power="high",
            args=self._program_args(
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                job_dir=job_dir,
                overrun_multiple=overrun_multiple,
                estimate_s=design.estimate_s,
                probe=design.probe.model_dump(mode="json"),
                command=build.command,
                code_root=self.ctx.code_root,
            ),
        )
        if verdict.decision != "kill_and_fix":
            return Continue(
                verdict,
                self.await_result,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                design=design,
                build=build,
                job_dir=job_dir,
                budget=budget,
                seen_multiple=overrun_multiple,
            )
        stopped = self.call(kill_job, job_dir=job_dir, reason="overrun")
        return self._repair(
            gate_id,
            gate_doc_path,
            design,
            budget,
            locus=verdict.fault_locus or "repo",
            component=verdict.component,
            reason=(
                f"killed at {overrun_multiple:.0f}× its estimate after "
                f"{stopped.wall_s:.0f}s: {verdict.diagnosis}"
            ),
            detail=verdict.fix_hint,
            where="a job running past its estimate",
        )

    def collect(
        self,
        gate_id: str,
        gate_doc_path: str,
        design: Design,
        build: Build,
        job_dir: str,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Classify what came back, with **zero model calls**."""
        collected = self.call(
            collect_job,
            job_dir=job_dir,
            repo_dir=self.ctx.repo_dir,
            cwd=build.cwd or self.ctx.repo_dir,
            result_file=build.result_file,
            memory_mb=design.memory_mb,
        )
        if collected.outcome == "over_resource":
            if budget.rescopes >= MAX_RESCOPES:
                return self._to_lead(
                    gate_id,
                    gate_doc_path,
                    escalation="max_rescopes",
                    notes=f"the experiment kept outgrowing its declared resources: "
                    f"{collected.reason}",
                    budget=budget,
                )
            return Continue(
                collected,
                self.design,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                rescope_reason=collected.reason,
                budget=budget.rescoped(),
            )
        if collected.outcome in ("crash", "invalid"):
            return self._repair(
                gate_id,
                gate_doc_path,
                design,
                budget,
                locus=collected.fault_locus,
                component="",
                reason=f"{collected.outcome}: {collected.reason}",
                detail=collected.stderr_tail,
                where="the measurement itself",
            )
        return Continue(
            collected,
            self.check,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            collected=collected.model_dump(mode="json"),
            budget=budget,
        )


    def check(
        self,
        gate_id: str,
        gate_doc_path: str,
        collected: Collected,
        budget: Budget = Budget(),
    ) -> Continue:
        """Judge the artifact against the gate doc's thresholds — and **never re-run**."""
        check = self.agent(
            "prompts/gate-check.md",
            returns=GateCheck,
            power="ultra",
            args={
                "repo_dir": self.ctx.repo_dir,
                "program_dir": self.ctx.program_dir,
                "gate_id": gate_id,
                "gate_doc_path": gate_doc_path,
                "result": collected.model_dump(mode="json"),
            },
        )
        if check.status == "approved":
            return Continue(check, self.record_pass, gate_id=gate_id, budget=budget)
        failed = check.failed_criteria
        if check.status == "killed":
            return Continue(
                check,
                self.record_kill,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed,
                notes=check.notes,
                budget=budget,
            )
        if budget.reworks >= MAX_REWORKS:
            return self._to_lead(
                gate_id,
                gate_doc_path,
                escalation="max_reworks",
                notes=(
                    f"{MAX_REWORKS} scientific reworks measured and missed. "
                    f"Last check: {check.notes}"
                ),
                failed_criteria=failed,
                budget=budget,
            )
        return Continue(
            check,
            self.design,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            rework_notes=check.notes,
            failed_criteria=failed,
            budget=budget.reworked(),
        )


    def record_pass(self, gate_id: str, budget: Budget = Budget()) -> Continue:
        """Write the approved gate's outcome, publish, and take the next gate."""
        result = self._record(gate_id)
        self._history("pass", gate_id)
        self._publish(f"record {gate_id} pass")
        return Continue(result, self.start, budget=budget.cycled())

    def record_kill(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        budget: Budget = Budget(),
    ) -> Continue:
        """Write the kill, then hand off to the research lead rather than terminating."""
        self._record(gate_id)
        self._history("kill", gate_id, note=notes)
        return Continue(
            None,
            self.program_review,
            origin="kill",
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria,
            notes=notes,
            escalation="",
            budget=budget.cycled(),
        )


    def lead_review(
        self,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        escalation: str = "",
        budget: Budget = Budget(),
        dossier: str = "",
    ) -> Continue | Await:
        """Judge whether the gate is dead, and route the program on the verdict."""
        _, lead_reviews = self._spent(budget)
        if lead_reviews >= MAX_LEAD_REVIEWS + budget.lead_review_grants:
            return self._blocked(
                f"This program has spent {lead_reviews} research-lead reviews "
                f"(cap {MAX_LEAD_REVIEWS}), and gate {gate_id or GOAL} needs another "
                "one.\n\nThat many reviews usually means the program is looping on a "
                "question its ladder cannot settle. Look at the progress file before "
                "answering.\n\nAnswering this gate authorizes exactly one more review; "
                "the loop then continues from where it stopped. To stop the program "
                "instead, set its ledger status and do not answer.",
                self.lead_review,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                budget=budget.granted_review(lead_reviews, MAX_LEAD_REVIEWS),
                dossier=dossier,
            )
        if not dossier:
            dossier = render_dossier(self._dossier(budget))
        review = self.agent(
            "prompts/research-lead-review.md",
            returns=LeadReview,
            power="ultra",
            args=self._program_args(
                goal=self.ctx.goal,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=[
                    c.model_dump(mode="json") for c in (failed_criteria or [])
                ],
                notes=notes,
                escalation=escalation,
                dossier=dossier,
            ),
        )
        self._history("lead_review", gate_id, note=review.verdict)
        if review.verdict == "revive":
            return Continue(
                review,
                self.program_review,
                origin="revive",
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                review=review,
                budget=budget,
            )
        if review.verdict == "new_direction":
            return Continue(
                review,
                self.new_direction,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                review=review,
                budget=budget,
            )
        return self._blocked(
            f"The research lead returned no actionable verdict for gate "
            f"{gate_id or GOAL} (got {review.verdict!r}; expected `revive` or "
            "`new_direction`).\n\nDecide what the gate should do, write it into the "
            "gate doc, and answer this gate — the lead re-reads the doc on resume.",
            self.lead_review,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            budget=budget,
            dossier=dossier,
        )

    def revive(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        budget: Budget = Budget(),
        escalation: str = "",
        notes: str = "",
    ) -> Continue:
        """Re-scope a gate that was killed or blocked for the wrong reason, then loop."""
        result = self.agent(
            "prompts/revive-gate.md",
            returns=ReviveResult,
            power="max",
            args=self._program_args(
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                lead_review=review,
                escalation=escalation,
                notes=notes,
            ),
        )
        note = result.status
        if result.prerequisite_gate_id:
            note += f"; prerequisite {result.prerequisite_gate_id} ahead of it"
        self._history("revive", gate_id, note=note)
        spent = budget.reviewed()
        self._persist(spent)
        self._publish(f"revive {gate_id} after lead review")
        return Continue(result, self.start, budget=spent)

    def new_direction(
        self,
        gate_id: str,
        gate_doc_path: str,
        review: LeadReview,
        budget: Budget = Budget(),
        dossier: str = "",
    ) -> Continue:
        """Define the direction that replaces a justifiably killed one — then check it."""
        if not dossier:
            dossier = render_dossier(self._dossier(budget))
        result = self.agent(
            "prompts/define-new-direction.md",
            returns=NewDirectionResult,
            power="ultra",
            args=self._program_args(
                goal=self.ctx.goal,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                lead_review=review,
                dossier=dossier,
            ),
        )
        self._history(
            "new_direction", gate_id, note=result.direction_name or result.core_question
        )
        spent = budget.reviewed()
        self._persist(spent)
        self._publish(f"redirect research after {gate_id}")
        failure = self._check_target()
        if not failure:
            return Continue(result, self.start, budget=spent)
        return Continue(
            result,
            self.recharter,
            review=ProgramReview(
                verdict="recharter",
                reason=(
                    f"The new direction **{result.direction_name or '(unnamed)'}** was "
                    "written, but its frozen target is not resolvable on its own eval."
                ),
                evidence=[failure],
            ),
            budget=spent,
            resolvability_failure=failure,
        )


    def program_review(
        self,
        origin: str,
        gate_id: str,
        gate_doc_path: str,
        failed_criteria: list[FailedCriterion],
        notes: str,
        escalation: str = "",
        review: LeadReview | None = None,
        budget: Budget = Budget(),
    ) -> Continue | Await:
        """Judge the *program* on its computed dossier, and route on a verdict that acts."""
        program_reviews, recharters = self._program_spent(budget)
        if program_reviews >= MAX_PROGRAM_REVIEWS + budget.program_review_grants:
            return self._blocked(
                f"This program has spent {program_reviews} program-level reviews "
                f"(cap {MAX_PROGRAM_REVIEWS}), and gate {gate_id or GOAL} needs another "
                f"one ({origin}).\n\nThat many program reviews means the lead keeps "
                "finding the program circling and keeps failing to stop it. Read the "
                "dossier the last one saw (`history.jsonl`, the progress file) before "
                "answering.\n\nAnswering this gate authorizes exactly one more review; "
                "the loop then continues from where it stopped. To stop the program "
                "instead, set its ledger status and do not answer.",
                self.program_review,
                origin=origin,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                review=review,
                budget=budget.granted_program_review(
                    program_reviews, MAX_PROGRAM_REVIEWS
                ),
            )
        dossier = self._dossier(budget)
        rendered = render_dossier(dossier)
        verdict = self.agent(
            "prompts/program-review.md",
            returns=ProgramReview,
            power="ultra",
            args=self._program_args(
                origin=origin,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                escalation=escalation,
                goal=self.ctx.goal,
                notes=notes,
                program_reviews_spent=program_reviews,
                program_reviews_max=MAX_PROGRAM_REVIEWS,
                recharters_spent=recharters,
                recharters_max=MAX_RECHARTERS,
                dossier=rendered,
            ),
        )
        spent = budget.program_reviewed()
        self._persist(spent)
        self._history(
            "program_review",
            gate_id,
            note=f"{origin}: {verdict.verdict} — {verdict.reason}",
            fingerprint=dossier.fingerprint,
        )
        if verdict.verdict == "continue":
            if origin == "revive" and review is not None:
                return Continue(
                    verdict,
                    self.revive,
                    gate_id=gate_id,
                    gate_doc_path=gate_doc_path,
                    review=review,
                    escalation=escalation,
                    notes=notes,
                    budget=spent,
                )
            if origin == "periodic":
                self._history("gate_selected", gate_id)
                return Continue(
                    verdict,
                    self.design,
                    gate_id=gate_id,
                    gate_doc_path=gate_doc_path,
                    budget=spent.fresh_gate(),
                )
            return Continue(
                verdict,
                self.lead_review,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                budget=spent,
                dossier=rendered,
            )
        if verdict.verdict in ("probe_first", "score_from_cache", "recharter"):
            if verdict.verdict == "recharter" and recharters >= MAX_RECHARTERS:
                return self._blocked(
                    f"This program has re-chartered its frozen target {recharters} "
                    f"times (cap {MAX_RECHARTERS}), and the lead wants to again:\n\n"
                    f"{verdict.reason}\n\nProposed: {verdict.recharter.metric or '?'} "
                    f"on {verdict.recharter.dataset or '?'}, "
                    f"{verdict.recharter.threshold or '?'} (n={verdict.recharter.n}) — "
                    f"{verdict.recharter.why_resolvable or '(no resolvability case)'}"
                    "\n\nA program that cannot settle on a resolvable target is a "
                    "program whose eval a person has to choose. Write the target into "
                    "the README's `Frozen target` table and answer this gate; the loop "
                    "reads it back and continues.",
                    self.start,
                    budget=spent,
                )
            return Continue(
                verdict,
                self.recharter,
                review=verdict,
                budget=spent,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
            )
        if verdict.verdict == "bank":
            return Continue(verdict, self.record_goal, outcome=GOAL_BANKED, budget=spent)
        if verdict.verdict == "stop_negative":
            return Continue(
                verdict, self.record_goal, outcome=GOAL_IMPOSSIBLE, budget=spent
            )
        question = (
            verdict.operator_question
            if verdict.verdict == "operator" and verdict.operator_question
            else (
                f"The program lead returned no actionable verdict for gate "
                f"{gate_id or GOAL} (got {verdict.verdict!r}; expected `continue`, "
                "`probe_first`, `score_from_cache`, `recharter`, `bank`, "
                "`stop_negative` or `operator`)."
            )
        )
        return self._blocked(
            f"{question}\n\nReason: {verdict.reason or '(none given)'}\n\nWrite the "
            "answer here and answer this gate; the program lead re-reads the record on "
            "resume.",
            self.program_review,
            origin=origin,
            gate_id=gate_id,
            gate_doc_path=gate_doc_path,
            failed_criteria=failed_criteria or [],
            notes=notes,
            escalation=escalation,
            review=review,
            budget=spent,
        )

    def recharter(
        self,
        review: ProgramReview,
        budget: Budget = Budget(),
        attempt: int = 0,
        resolvability_failure: str = "",
        gate_id: str = "",
        gate_doc_path: str = "",
        failed_criteria: list[FailedCriterion] | None = None,
        notes: str = "",
        escalation: str = "",
    ) -> Continue | Await:
        """Apply a program-level verdict to the program folder, in place, then loop."""
        result = self.agent(
            "prompts/program-recharter.md",
            returns=RecharterResult,
            power="max",
            args=self._program_args(
                review=review.model_dump(mode="json"),
                dossier=render_dossier(self._dossier(budget)),
                resolvability_failure=resolvability_failure,
                gate_template=str(GATE_TEMPLATE),
                today=date.today().isoformat(),
            ),
        )
        rechartered = review.verdict == "recharter" or bool(result.new_target.n)
        failure = ""
        if rechartered:
            failure = self._check_target(result.new_target)
        if failure and attempt < MAX_RECHARTER_FIXES:
            self._history("recharter", note=f"unresolvable, retrying: {failure}")
            self._publish("record unresolved target recharter")
            return Continue(
                result,
                self.recharter,
                review=review,
                budget=budget,
                attempt=attempt + 1,
                resolvability_failure=failure,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
            )
        if failure:
            self._history("recharter", note=f"unresolvable, parked: {failure}")
            self._publish("record blocked target recharter")
            return self._blocked(
                f"The re-chartered target is still not resolvable after "
                f"{attempt + 1} attempts:\n\n{failure}\n\nThe lead's case: "
                f"{result.new_target.why_resolvable or '(none)'}\n\nSupply a bigger "
                "eval or a different metric in the README's `Frozen target` table and "
                "answer this gate; the loop reads it back and continues.",
                self.start,
                budget=budget,
            )
        event = {
            "probe_first": "probe_ordered",
            "score_from_cache": "cache_directive",
        }.get(review.verdict, "recharter")
        spent = budget.rechartered() if rechartered else budget
        self._history(
            event,
            review.probe.gate_id or review.cache_gate_id,
            note=result.reason or review.reason,
        )
        self._persist(spent)
        self._publish(f"record {event.replace('_', ' ')} decision")
        if escalation and review.verdict != "probe_first":
            return Continue(
                result,
                self.lead_review,
                gate_id=gate_id,
                gate_doc_path=gate_doc_path,
                failed_criteria=failed_criteria or [],
                notes=notes,
                escalation=escalation,
                budget=spent,
            )
        return Continue(result, self.start, budget=spent)


    def goal_review(self, budget: Budget = Budget()) -> Continue | Await:
        """Every reachable gate passed — so judge the program against its North star."""
        extensions_spent, _ = self._spent(budget)
        review = self.agent(
            "prompts/lead-goal-review.md",
            returns=GoalReview,
            power="ultra",
            args=self._program_args(
                code_root=self.ctx.code_root,
                goal=self.ctx.goal,
                extensions_spent=extensions_spent,
                extensions_max=MAX_EXTENSIONS,
                dossier=render_dossier(self._dossier(budget)),
            ),
        )
        if review.verdict == "reached":
            return Continue(review, self.record_goal, outcome=GOAL_REACHED, budget=budget)
        if review.verdict == "banked":
            return Continue(review, self.record_goal, outcome=GOAL_BANKED, budget=budget)
        if review.verdict == "impossible":
            return Continue(
                review, self.record_goal, outcome=GOAL_IMPOSSIBLE, budget=budget
            )
        if review.verdict == "extend":
            if extensions_spent >= MAX_EXTENSIONS + budget.extension_grants:
                return self._blocked(
                    f"This program has extended itself {extensions_spent} times "
                    f"(cap {MAX_EXTENSIONS}) and the lead wants another gate:\n\n"
                    f"{review.next_gate_title or '(untitled)'} — "
                    f"{review.next_gate_question or '(no question stated)'}\n\n"
                    f"North star gap: {review.north_star_gap or '(not stated)'}\n\n"
                    "A program at this cap is usually deferring a verdict it could "
                    "give: read the ladder and decide whether the strongest result so "
                    "far is bankable. Answering authorizes exactly one more "
                    "extension.",
                    self.goal_review,
                    budget=budget.granted_extension(extensions_spent, MAX_EXTENSIONS),
                )
            return Continue(
                review,
                self.extend,
                review=review,
                budget=budget,
            )
        return self._blocked(
            f"The goal review returned no actionable verdict (got "
            f"{review.verdict!r}; expected `reached`, `banked`, `impossible` or "
            "`extend`).\n\nThe ladder is exhausted, so the program cannot proceed "
            "without one. Record your judgement in the program README and answer this "
            "gate; the lead re-reads it on resume.",
            self.goal_review,
            budget=budget,
        )

    def extend(self, review: GoalReview, budget: Budget = Budget()) -> Continue:
        """Append the next gate to the ladder, then loop — it is now the lowest non-PASS gate, so `start` picks it up."""
        result = self.agent(
            "prompts/extend-program.md",
            returns=ExtendResult,
            power="max",
            args=self._program_args(
                code_root=self.ctx.code_root, goal=self.ctx.goal, goal_review=review
            ),
        )
        spent = budget.extended()
        self._persist(spent)
        self._publish("extend the research gate ladder")
        return Continue(result, self.start, budget=spent)


    def record_goal(self, outcome: str, budget: Budget = Budget()) -> Done:
        """Record a goal verdict, conclude the program in its ledger, publish, end clean."""
        result = self._record(GOAL, forced=outcome)
        self._history("goal", GOAL, note=outcome)
        self._persist(budget, status=GOAL_STATUS.get(outcome, "active"))
        self._publish(f"record goal {outcome.lower()}")
        return Done(result)


workflow = Registry("research", package=__package__).add_blueprints(
    blueprint, gate_blueprint
).stub_agents(
    {
        "select-next-gate": {"gate_id": ""},
        "lead-goal-review": {"verdict": "reached"},
        "program-review": {"verdict": "continue"},
        "program-recharter": {"status": "written"},
    }
)
main = console_script(workflow.entry_point(Research))
