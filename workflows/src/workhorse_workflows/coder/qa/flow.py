"""One QA owner plans, runs, audits and repairs a story's QA through its subagents, and the run checks it."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed

from workhorse_workflows.coder.qa.nodes import (
    QA_SCRATCH_DIRNAME,
    check_sentinel_ids,
    clear_qa_evidence,
    detect_regression_suites,
    ensure_stack,
    flush_root_screenshots,
    lint_qa_plan,
    qa_tools_catalog,
    run_qa_plan,
    run_regression_suite,
    validate_qa_plan,
    verify_qa_dry_run,
    verify_qa_evidence,
)
from workhorse_workflows.coder.qa.report import (
    failed_scenario_ids,
    failed_scenarios_arg,
    fallback_finding,
    gate_text,
    qa_only_arg,
    refix_findings,
    regression_text,
    stack_failures,
    unclassified_failure,
    unfinished_run,
    unproved_findings,
)
from workhorse_workflows.coder.shared import paths, roles, work
from workhorse_workflows.coder.shared.backlog import file_backlog_items
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.docs import detect_okf_docs, features_root
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
from workhorse_workflows.coder.shared.plan import plan_summary, resolve_impl_context
from workhorse_workflows.coder.shared.provenance import resolve_story_sources
from workhorse_workflows.coder.shared.resolution import RESOLVER_POWER, answered, resolver_args
from workhorse_workflows.coder.shared.review import check_feedback
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.qa import (
    QaFinding,
    QaFlowResult,
    QaFlowStatus,
    QaOwnerResult,
    QaPlanRun,
    QaResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.coder.shared.story import prepare_story, stamp_specs
from workhorse_workflows.coder.shared.worktree import code_changed, snapshot_code_state
from workhorse_workflows.kit.telemetry import counter_labels


class Qa(Workflow):
    """QA one story through one owner session, then rerun and gate what it claims."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    target_env: str = "local"
    stop_at_first_verdict: bool = False
    preexisting: tuple[str, ...] = ()

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack})

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks")

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its `qa/` directory."""
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        if not ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r}. The story could not be resolved, so "
                "there is nothing to QA."
            )
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "qa", self.BUDGET_LABELS)

    @property
    def _session(self) -> str:
        return f"qa:{self.ctx.story_slug}"

    def _dirs(self) -> list[str]:
        """The repos this story's plan touches: every agent turn's `add_dirs`."""
        return list(self.output(resolve_impl_context).affected_repo_paths)

    def start(self) -> Continue:
        """Clear the last run's evidence, decode what the story touched, and check its context and stack."""
        self.call(snapshot_code_state, self.docs_path)
        self.call(clear_qa_evidence, self.ctx.spec_dir)
        impl = self.call(resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path)
        if self._sourced:
            sources = self.call(
                resolve_story_sources,
                tuple(impl.dispatch_list),
                self.ctx.story_slug,
                self.ctx.story_id,
                self.docs_path,
            )
            if sources.status != "valid":
                raise WorkflowFailed(
                    "story source provenance could not be resolved: " + "; ".join(sources.errors)
                )
        okf = self.call(detect_okf_docs, self.docs_path)
        return Continue(okf, self.work, report="\n\n".join(self._preflight()))

    @property
    def _sourced(self) -> bool:
        return bool(self.workspace_file and self.ctx.story_id)

    def _preflight(self) -> list[str]:
        """The OKF context packet and the QA stack, as failures the owner repairs."""
        impl = self.output(resolve_impl_context)
        build = self.call(
            build_okf_context,
            self.ctx.spec_dir,
            self.ctx.story_path,
            features_root(self),
            tuple(impl.qa_source_roots),
            "HEAD",
            "WORKTREE",
            self.docs_path,
            preexisting=tuple(self.preexisting),
            story_sources=self.output(resolve_story_sources).sources if self._sourced else (),
        )
        context = self.call(validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path)
        failures = []
        if context.status != "passed":
            failures.append(gate_text("the OKF context packet", context.notes))
        return failures + stack_failures(self.call(ensure_stack, self.docs_path))

    def _owner_args(self) -> dict[str, Any]:
        """What the owner reads about its story, its plan and the tools it may drive."""
        impl = self.output(resolve_impl_context)
        spec_dir = self.ctx.spec_dir
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id or self.ctx.story_slug,
            "epic": self.epic,
            "qa_dir": self.ctx.qa_dir,
            "qa_scratch_dir": QA_SCRATCH_DIRNAME,
            "docs_path": self.docs_path,
            "target_env": self.target_env,
            "runtime_python": sys.executable,
            "verification_setup": impl.verification_setup,
            "fixtures": [f.model_dump() for f in impl.fixtures],
            "shared_packages": impl.shared_packages,
            "qa_run_plan": [r.model_dump() for r in impl.qa_run_plan],
            "plan_services": self.call(plan_summary, spec_dir).text,
            "qa_only_scenarios": qa_only_arg(spec_dir),
            "qa_tools": self.call(qa_tools_catalog, self.docs_path).tools,
            "standing_plan": self._standing_plan(),
        }

    def _standing_plan(self) -> bool:
        """Does a `qa_plan.py` already stand that lints and validates against the packet?"""
        spec_dir = self.ctx.spec_dir
        if not spec_dir or not (Path(spec_dir) / "qa_plan.py").is_file():
            return False
        if self.call(lint_qa_plan, spec_dir, self.docs_path).status != "passed":
            return False
        return self.call(validate_qa_plan, spec_dir, self.docs_path).status == "passed"

    def work(
        self,
        report: str = "",
        operator_context: str = "",
        failed_scenarios: list[dict[str, Any]] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the owner turn: its subagents plan, run, audit and repair the story's QA."""
        self.logger.info("owning QA for %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "qa-story", returns=QaOwnerResult)
        result: QaOwnerResult = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("qa"),
            session=self._session,
            add_dirs=self._dirs(),
            args=turn.args
            | self._owner_args()
            | {
                "report": report,
                "operator_context": operator_context,
                "failed_scenarios": failed_scenarios or [],
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "blocked":
            return self._block(result, result.notes, "the QA turn", blocks)
        return Continue(
            result,
            self.check,
            findings=[f.model_dump() for f in result.findings],
            proved=list(dict.fromkeys(s.strip() for s in result.proved_scenarios if s.strip())),
            laps=laps,
            blocks=blocks,
        )

    def check(
        self,
        findings: list[dict[str, Any]] | None = None,
        proved: list[str] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await | Done:
        """Rerun the plan the owner left, gate what it claims, and send what failed back."""
        found = [QaFinding.model_validate(f) for f in findings or []]
        failures = self._preflight() or self._plan_failures(proved or [])
        if failures:
            return self._lap(None, failures, laps, blocks)
        self.logger.info("running the QA plan", extra={"activity": True})
        run = self.call(run_qa_plan, self.ctx.spec_dir, self.docs_path)
        self.call(file_backlog_items, self.ctx.spec_dir, self.docs_path)
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if run.status == "failed" and (found or self.stop_at_first_verdict):
            return self._failed(run, found)
        if run.status == "failed":
            ids = failed_scenario_ids(run)
            failed = failed_scenarios_arg(self.ctx.spec_dir, ids)
            return self._lap(run, [unclassified_failure(run, ids)], laps, blocks, failed)
        if run.status != "passed":
            failures = [unfinished_run(run)]
        elif found:
            failures = [unproved_findings(found)]
        else:
            failures = self._pass_failures(run)
        if not failures:
            self.logger.info("QA passed for %s", self.ctx.story_slug)
            return self._finish("passed", run)
        if self.stop_at_first_verdict and run.status == "passed" and not found:
            notes = "\n\n".join(failures)
            return self._finish("refix", run, [fallback_finding(self.ctx.qa_dir, notes)])
        return self._lap(run, failures, laps, blocks)

    def _plan_failures(self, proved: list[str]) -> list[str]:
        """The plan's lint, its validation against the packet, and the dry runs it claims."""
        lint = self.call(lint_qa_plan, self.ctx.spec_dir, self.docs_path)
        if lint.status != "passed":
            return [gate_text("qa_plan.py lint", lint.notes)]
        validation = self.call(validate_qa_plan, self.ctx.spec_dir, self.docs_path)
        if validation.status != "passed":
            return [gate_text("qa_plan.py validation", validation.notes)]
        if not proved:
            return []
        gate = self.call(verify_qa_dry_run, self.ctx.spec_dir, tuple(proved))
        return [] if gate.status == "passed" else [gate_text("the dry runs", gate.notes)]

    def _pass_failures(self, run: QaPlanRun) -> list[str]:
        """The gates a passed run must also clear before the story is believed."""
        evidence = self.call(verify_qa_evidence, self.ctx.spec_dir, run.status, run.notes)
        if evidence.status != "passed":
            return [gate_text("the QA evidence", evidence.notes)]
        note = self.call(check_feedback, str(self.run_dir))
        if note.present:
            return [gate_text("operator feedback", note.content)]
        suites = self.call(detect_regression_suites, self.ctx.spec_dir)
        if suites.suites:
            regression = self.call(
                run_regression_suite,
                self.ctx.spec_dir,
                self.ctx.qa_dir,
                [s.model_dump() for s in suites.suites],
            )
            if regression.status not in {"passed", "skipped"}:
                return [regression_text(regression)]
        self.call(flush_root_screenshots, self.ctx.spec_dir)
        sentinels = self.call(check_sentinel_ids, self.ctx.story_slug)
        if sentinels.status != "passed":
            return [gate_text("sentinel ids", sentinels.notes)]
        return []

    def _failed(self, run: QaPlanRun, found: list[QaFinding]) -> Done:
        """A failed run with its findings: the dev owner's to fix, or the tracker's in dev."""
        if self.target_env == "dev":
            self.logger.info("QA failed for %s in dev, reported", self.ctx.story_slug)
            return self._finish("passed", run, found)
        self.logger.info("QA found product defects in %s", self.ctx.story_slug)
        return self._finish("refix", run, refix_findings(found, self.ctx.qa_dir, run.notes))

    def _lap(
        self,
        result: object,
        failures: list[str],
        laps: int,
        blocks: int,
        failed: list[dict[str, Any]] | None = None,
    ) -> Continue | Await:
        text = "\n\n".join(failures)
        if laps >= MAX_LAPS:
            notes = f"{text}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(result, notes, "the checks", blocks)
        return Continue(
            result,
            self.work,
            report=text,
            failed_scenarios=failed or [],
            laps=laps + 1,
            blocks=blocks,
        )

    def _finish(
        self, status: QaFlowStatus, run: QaPlanRun, findings: list[QaFinding] | None = None
    ) -> Done:
        before = self.output(snapshot_code_state).status
        changed = self.call(code_changed, before=before, docs_path=self.docs_path)
        if status != "refix":
            self.reset_session(self._session)
        return Done(
            QaFlowResult(
                status=status,
                qa=QaResult(status=run.status, notes=run.notes),
                findings=findings or [],
                docs_recheck_required=changed.changed,
            )
        )

    def _block(self, result: object, notes: str, where: str, blocks: int) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks)
        return Continue(result, self.resolve, notes=notes, where=where, blocks=blocks)

    def _ask(
        self, notes: str, where: str, blocks: int, result: OperatorResolution | None = None
    ) -> Await:
        gate = escalation(
            self,
            block_kind="qa",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
        )
        return Await(context_path(self), gate.body, self.read_operator, blocks=blocks + 1)

    def resolve(self, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args=resolver_args(self, block_kind="qa", notes=notes, docs_path=self.docs_path),
        )
        if answered(self, result, "qa"):
            return Continue(result, self.read_operator, blocks=blocks + 1)
        return self._ask(notes, where, blocks, result)

    def read_operator(self, blocks: int = 0) -> Continue | Done:
        """Log the answer, then resume the owner's session with it in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        work.log_answer(self.run_dir, f"{self.ctx.story_slug}: {answer.scope}", answer.content)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the answer to the epic, so the run replans")
            self.reset_session(self._session)
            return Done(QaFlowResult(status="replan", operator_notes=answer.content))
        return Continue(answer, self.work, operator_context=answer.content, blocks=blocks)


__all__ = ["Qa"]
