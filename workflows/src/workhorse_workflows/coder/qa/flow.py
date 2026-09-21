"""Plan QA for a story, run it, and refuse to believe it passed."""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, Protocol

from workhorse.pyflow import (
    AgentTimeout,
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.shared import paths, qa_support, roles
from workhorse_workflows.coder.shared.backlog import file_backlog_items
from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.shared.dev import (
    plan_summary,
    read_operator_context,
    resolve_impl_context,
    resolve_story_sources,
)
from workhorse_workflows.coder.shared.docs import detect_okf_docs, features_root
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
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
from workhorse_workflows.coder.shared.review import check_feedback
from workhorse_workflows.coder.shared.scenarios import qa_only_scenarios
from workhorse_workflows.coder.shared.story import prepare_story, stamp_specs
from workhorse_workflows.coder.shared.schemas.dev import OperatorGate, OperatorResolution
from workhorse_workflows.coder.shared.schemas.qa import (
    AssessmentRecord,
    AuditRecord,
    ContextRepair,
    FixWorklist,
    QaAssessment,
    QaAudit,
    QaFinding,
    QaFlowResult,
    QaLoop,
    QaPlanResult,
    QaReport,
    QaPlanRun,
    QaResult,
    QaRunResult,
    QaTriage,
    RegressionFix,
    SetupResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels

UNBOUNDED = float("inf")

_OVERRAN_PLAN = (
    "The previous turn was stopped at its wall-clock budget before it could finish. "
    "The file on disk is the draft it had written by then, not a finished plan: expect it "
    "to end mid-scenario or mid-statement. Complete it from where it stands — keep every "
    "scenario already written and do not re-author the file."
)
_OVERRAN_REPAIR = (
    "The previous repair turn was stopped at its wall-clock budget partway through its "
    "worklist. The file on disk has some of those edits applied and not the rest. Continue "
    "from there — re-applying an edit that is already in place is wasted budget, and "
    "starting the file over discards the ones that landed."
)
_SWITCHED = (
    "A {spent} was already spent on this failure, and the suite then failed identically — "
    "the same scenarios, the same number of assertions in. So the defect is most likely not "
    "where that repair was looking. Treat what it repaired as correct and look for the cause "
    "on the other side: if the plan was repaired, the product is the suspect, and if the "
    "product was fixed, suspect how the plan reads it — an assertion that samples a value "
    "without waiting for it fails in the exact shape of a broken product."
)

QA_LANE_BUDGET_S = 3300
PLAN_LANE_BUDGET_S = 2400

MAX_QA_REWORKS = 8
MAX_CONTEXT_REWORKS = 3
MAX_QA_BLOCKS = 3
MAX_PLAN_REWORKS = 6
MAX_PLAN_VALIDATION_REWORKS = 3
MAX_TOTAL_PLAN_LAPS = 8
MAX_BLOCKING_AUDITS = 2
MAX_SETUP_REWORKS = 2
MAX_FIX_ITEM_REWORKS = 2
MAX_REGRESSION_FIXES = 3
MAX_TRIAGE_SCOPES = 2
MAX_CHAIN_LAPS = 4


def _finding(passed: bool, notes: str) -> str:
    """A gate's notes when it failed, and nothing when it passed."""
    return "" if passed else notes


def _blocked_problems(result: QaPlanRun) -> tuple[str, ...]:
    """The runtime requirements a `blocked` run named, sorted; empty for every other status."""
    if result.status != "blocked":
        return ()
    problems = result.ostler.get("problems")
    if not isinstance(problems, list):
        return ()
    return tuple(sorted(str(problem) for problem in problems))


def _failure_signature(result: QaPlanRun) -> tuple[str, ...]:
    """What a failing run failed at, as a fingerprint two runs can be compared on."""
    if result.status != "failed":
        return ()
    scenarios = result.ostler.get("scenarios")
    if not isinstance(scenarios, dict):
        return ()
    return tuple(
        sorted(
            f"{name}:{outcome.get('status')}:{outcome.get('assertions')}/{outcome.get('failures')}"
            for name, outcome in scenarios.items()
            if isinstance(outcome, dict) and outcome.get("status") != "passed"
        )
    )


def _last_run(flow: Qa) -> QaPlanRun | None:
    """The latest `run_qa_plan` payload the run recorded — `None` before the first run."""
    try:
        return flow.output(run_qa_plan)
    except NodeNotRunError:
        return None


def _run_failures(flow: Qa) -> tuple[str, ...]:
    """What the latest QA run failed at, as `_failure_signature` renders it."""
    result = _last_run(flow)
    return _failure_signature(result) if result is not None else ()


def _failed_scenarios(flow: Qa) -> tuple[str, ...]:
    """The ids alone of the scenarios the latest QA run did not pass."""
    result = _last_run(flow)
    return _failed_scenario_ids(result) if result is not None else ()


def _failed_scenario_ids(result: QaPlanRun) -> tuple[str, ...]:
    """The ids alone of the scenarios a failing run did not pass, sorted."""
    if result.status != "failed":
        return ()
    scenarios = result.ostler.get("scenarios")
    if not isinstance(scenarios, dict):
        return ()
    return tuple(
        sorted(
            str(name)
            for name, outcome in scenarios.items()
            if isinstance(outcome, dict) and outcome.get("status") != "passed"
        )
    )


def _finding_line(finding: QaFinding) -> str:
    """One structured finding as the line whoever repairs it is briefed with."""
    issue = finding.issue.rstrip(".")
    return (
        f"{finding.id} [{finding.scope}/{finding.kind}] {finding.target}: {issue}. "
        f"Repair: {finding.repair}"
    )


def _brief(findings: Sequence[QaFinding], notes: str) -> str:
    """The repair brief, composed from the findings rather than taken from the prose."""
    lines = [_finding_line(finding) for finding in findings]
    if notes.strip():
        lines.append(f"Summary: {notes.strip()}")
    return "\n".join(lines)


class RoutedFindings(NamedTuple):
    """One gate's findings split by who has the authority to repair them."""

    plan: list[QaFinding]
    product_test: list[QaFinding]
    stack: list[QaFinding]


def _route_findings(findings: Sequence[QaFinding]) -> RoutedFindings:
    """Partition findings by `scope` — the closed vocabulary is what makes this decidable."""
    return RoutedFindings(
        plan=[finding for finding in findings if finding.scope == "plan"],
        product_test=[finding for finding in findings if finding.scope == "product-test"],
        stack=[finding for finding in findings if finding.scope == "stack"],
    )


def _repeating(loop: QaLoop, lap: str, failures: tuple[str, ...]) -> bool:
    """Has the last repair left the run failing at exactly what it failed at before?"""
    return bool(failures) and loop.repaired_lap == lap and failures == loop.repaired_failures

def _rejection(loop: QaLoop, kind: str) -> str:
    """This refusal as one comparable line: which gate raised it, and what it said."""
    return f"{kind}: {' '.join(loop.plan_validation_notes.split())}"

class _ReportState(Protocol):
    """A terminal report state, as `_blocked_report` resumes it: one keyword, the loop."""

    def __call__(self, loop: QaLoop) -> Await | Done: ...


def _escalation(
    flow: Qa,
    loop: QaLoop,
    result: OperatorResolution | None = None,
    findings: Sequence[Finding] = (),
) -> OperatorGate:
    """The gate body for this block — see `coder.shared.escalation`."""
    return escalation(
        flow,
        block_kind="qa",
        where=(
            f"last lap: {loop.repaired_lap or 'none'}; "
            f"{loop.qa_rework} code rework, {loop.plan_rework} plan repair, "
            f"{loop.context_rework} context repair, {loop.setup_rework} setup repair"
        ),
        notes=loop.block_notes,
        number=loop.escalations,
        result=result,
        findings=findings,
    )

def _note_lane_budget(loop: QaLoop, logger: logging.Logger) -> None:
    """Log a QA lane over its advisory wall-clock budget."""
    if loop.clock.seconds >= QA_LANE_BUDGET_S:
        logger.info(
            "the QA lane has spent %.0fs of its %ds advisory budget — continuing, the "
            "lap ceilings decide when this story stops",
            loop.clock.seconds,
            QA_LANE_BUDGET_S,
            extra={"activity": True},
        )

def _note_plan_budget(loop: QaLoop, logger: logging.Logger) -> None:
    """The same, for the plan lane."""
    if loop.clock.plan_seconds >= PLAN_LANE_BUDGET_S:
        logger.info(
            "the QA plan lane has spent %.0fs of its %ds advisory budget — continuing, "
            "the plan-lap ceilings decide when this plan stops",
            loop.clock.plan_seconds,
            PLAN_LANE_BUDGET_S,
            extra={"activity": True},
        )

class Qa(Workflow):
    """Run a story's QA plan, gate the evidence, audit the pass, and bound every retry."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    target_env: str = "local"
    stop_at_first_verdict: bool = False
    triage_scope: int = 0
    preexisting: tuple[str, ...] = ()

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its `qa/` directory, and pick up the conversation the lane before this one was having."""
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        if not ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r} — the story could not be resolved, so "
                "there is nothing to QA."
            )
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    @property
    def _chain(self) -> str:
        """The session chain `repair_plan` runs on, keyed per story."""
        return f"qa-plan-repair:{self.ctx.story_slug}"

    _WORKLISTS = ("plan-repair", "feedback", "regression-fix")

    def _reset_chains(self) -> None:
        """Drop every chain this flow opens for the current story."""
        for worklist in self._WORKLISTS:
            self.reset_session(f"qa-{worklist}:{self.ctx.story_slug}")

    def _ends(self, result: QaFlowResult) -> Done:
        """End the flow, and every chain it opened with it."""
        self._reset_chains()
        return Done(result)

    def _first_verdict_ends(self, loop: QaLoop) -> Done:
        """`stop_at_first_verdict`'s terminal: report the verdict as it stands, `inconclusive`."""
        return self._ends(
            QaFlowResult(
                status="inconclusive",
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack})

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = (
        "context_rework",
        "plan_rework",
        "plan_validation_rework",
        "plan_rework_total",
        "plan_judgement_rework",
        "qa_rework",
        "setup_rework",
        "regression_fix",
        "triage_scope",
        "audit_rework",
        "plan_overruns",
    )

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on, and what each gate last decided."""
        loop = params.get("loop")
        if not isinstance(loop, QaLoop):
            return self.labels()
        carried = loop.model_dump() | {
            "plan_rework_total": loop.plan_rework_total,
            "plan_judgement_rework": loop.plan_judgement_rework,
            "plan_overruns": loop.clock.overruns,
        }
        verdicts = loop.assessment.dimensions() | loop.audit.dimensions()
        return (
            self.labels()
            | counter_labels(carried, "qa", self.BUDGET_LABELS)
            | verdict_labels(verdicts, "qa", tuple(verdicts))
        )


    def start(self) -> Continue:
        """Clear the last run's evidence and decode what this story actually touched."""
        self._reset_chains()
        self.call(clear_qa_evidence, self.ctx.spec_dir)
        impl = self.call(
            resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path
        )
        if self.workspace_file and self.ctx.story_id:
            sources = self.call(
                resolve_story_sources,
                tuple(impl.dispatch_list),
                self.ctx.story_slug,
                self.ctx.story_id,
                self.docs_path,
            )
            if sources.status != "valid":
                raise WorkflowFailed(
                    "story source provenance could not be resolved: "
                    + "; ".join(sources.errors)
                )
        okf = self.call(detect_okf_docs, self.docs_path)
        return Continue(
            okf,
            self.build_context,
            loop=QaLoop(
                triage_scope=self.triage_scope,
                docs_recheck_required=False,
            ),
        )

    def build_context(self, loop: QaLoop) -> Continue | Await | Done:
        """Diff the implementation against the OKF graph and demand a mappable packet."""
        self.reset_session(self._chain)
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
            story_sources=(
                self.output(resolve_story_sources).sources
                if self.workspace_file and self.ctx.story_id
                else ()
            ),
        )
        result = self.call(
            validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path
        )
        loop = loop.update(
            context_status=result.status,
            context_notes=_finding(result.status == "passed", result.notes),
            clock=loop.clock.model_copy(update={"chain_laps": 0}),
            plan_rejections=(),
        )
        if result.status == "passed":
            return Continue(result, self.stack, loop=loop)
        if loop.context_rework >= MAX_CONTEXT_REWORKS:
            return self._exhausted(loop, f"{loop.context_rework} OKF-context repair")
        return Continue(result, self.repair_context, loop=loop)

    def repair_context(self, loop: QaLoop) -> Continue | Await | Done:
        """Ask an agent to make the packet mappable, once per rework the budget allows."""
        self.logger.info("repairing the QA obligation packet", extra={"activity": True})
        started = time.monotonic()
        turn = roles.turn(self, "repair-qa-context", returns=ContextRepair)
        reply = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="low",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "context_notes": loop.context_notes,
            },
        )
        loop = (
            loop.charged(time.monotonic() - started)
            .require_docs_recheck()
            .with_qa(reply.as_qa_result())
        )
        if reply.status == "repaired":
            return Continue(
                reply, self.build_context, loop=loop.update(context_rework=loop.context_rework + 1)
            )
        return self._gate(reply, loop)


    def plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Author the QA plan, forget every previous gate's findings, and parse the result."""
        self.logger.info("planning QA for %s", self.ctx.story_slug, extra={"activity": True})
        if self._standing_plan():
            self.logger.info(
                "a standing qa_plan.py lints and validates against the packet — "
                "adopting it without an authoring turn",
                extra={"activity": True},
            )
            return self._validated(loop)
        _note_plan_budget(loop, self.logger)
        overran = ""
        started = time.monotonic()
        drafted: QaPlanResult | None = None
        try:
            turn = roles.turn(self, "plan-qa", returns=QaPlanResult)
            drafted = self.agent(
                turn.prompt,
                returns=turn.returns,
                power="medium",
                session=backbone(self),
                timeout=1200,
                retries=0,
                add_dirs=self._dirs(),
                args=turn.args | self._plan_args(loop),
            )
        except AgentTimeout:
            self.logger.info(
                "the QA-plan turn was stopped at its budget — validating what it wrote",
                extra={"activity": True},
            )
            overran = _OVERRAN_PLAN
        loop = loop.charged(time.monotonic() - started, plan=True, overran=bool(overran))
        if drafted is not None and drafted.blocked:
            return self._refused(drafted, loop, "the QA planner")
        proved: tuple[str, ...] = ()
        if drafted is not None:
            proved = tuple(
                dict.fromkeys(str(s).strip() for s in drafted.proved_scenarios if str(s).strip())
            )
        return self._validated(loop, overran=overran, dry_run=proved)

    def repair_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Edit the cited part of a plan that already exists, leaving the rest byte-identical."""
        self.logger.info("repairing the QA plan for %s", self.ctx.story_slug,
                         extra={"activity": True})
        laps = loop.clock.chain_laps
        if laps >= MAX_CHAIN_LAPS or _repeating(loop, "QA-plan repair", _run_failures(self)):
            self.reset_session(self._chain)
            laps = 0
        loop = loop.update(clock=loop.clock.model_copy(update={"chain_laps": laps + 1}))
        overran = ""
        repaired: tuple[str, ...] = ()
        result: QaPlanResult | None = None
        started = time.monotonic()
        try:
            turn = roles.turn(self, "repair-qa-plan", returns=QaPlanResult)
            result = self.agent(
                turn.prompt,
                returns=turn.returns,
                power="low",
                timeout=2700,
                retries=0,
                add_dirs=self._dirs(),
                args=turn.args | self._plan_args(loop),
                session=self._chain,
            )
            repaired = tuple(str(scenario) for scenario in result.repaired_scenarios)
        except AgentTimeout:
            self.logger.info(
                "the QA-plan repair turn was stopped at its budget — validating what it wrote",
                extra={"activity": True},
            )
            overran = _OVERRAN_REPAIR
        loop = loop.charged(time.monotonic() - started, plan=True, overran=bool(overran))
        if result is not None and result.blocked:
            return self._refused(result, loop, "the QA-plan repair")
        return self._validated(
            loop,
            overran=overran,
            dry_run=tuple(sorted({*_failed_scenarios(self), *repaired})),
        )

    def _standing_plan(self) -> bool:
        """Does a `qa_plan.py` already stand that lints and validates against the packet?"""
        spec_dir = self.ctx.spec_dir
        if not spec_dir or not (Path(spec_dir) / "qa_plan.py").is_file():
            return False
        if self.call(lint_qa_plan, spec_dir, self.docs_path).status != "passed":
            return False
        return self.call(validate_qa_plan, spec_dir, self.docs_path).status == "passed"

    def _plan_args(self, loop: QaLoop) -> dict[str, object]:
        """Every diagnostic the loop collected, for whichever plan turn is about to run."""
        impl = self.output(resolve_impl_context)
        tools = self.call(qa_tools_catalog, self.docs_path)
        spec_abs = Path(self.ctx.spec_dir) if self.ctx.spec_dir else None
        failed = _failed_scenarios(self)
        failed_assertions = (
            qa_support.failed_assertions(qa_support.scored_run_log(spec_abs))
            if spec_abs and failed
            else {}
        )
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id or self.ctx.story_slug,
            "epic": self.epic,
            "qa_dir": self.ctx.qa_dir,
            "qa_scratch_dir": QA_SCRATCH_DIRNAME,
            "docs_path": self.docs_path,
            "target_env": self.target_env,
            "verification_setup": impl.verification_setup,
            "fixtures": [f.model_dump() for f in impl.fixtures],
            "shared_packages": impl.shared_packages,
            "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
            "qa_only_scenarios": [
                {"title": s.title, "ac": s.ac, "level": s.level}
                for s in qa_only_scenarios(spec_abs, "")
            ],
            "failed_scenarios": [
                {"id": scenario, "failed_assertions": failed_assertions.get(scenario, [])}
                for scenario in failed
            ],
            "context_status": loop.context_status,
            "context_notes": loop.context_notes,
            "plan_validation_notes": loop.plan_validation_notes,
            "run_assessment_notes": loop.assessment.notes,
            "audit_notes": loop.audit.notes,
            "evidence_notes": loop.qa.notes,
            "qa_tools": tools.tools,
        }

    def _validated(
        self, loop: QaLoop, overran: str = "", dry_run: tuple[str, ...] = ()
    ) -> Continue | Await | Done:
        """The tail both plan turns share: clear the brief, stamp, parse, route on the parse."""
        loop = loop.cleared()
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        lint = self.call(lint_qa_plan, self.ctx.spec_dir, self.docs_path)
        if lint.status != "passed":
            notes = lint.notes
            if overran:
                notes = f"{overran}\n\n{notes}".strip()
            loop = loop.update(plan_validation_notes=_finding(False, notes))
            return self._guard_plan_validation(lint, loop)
        validation = self.call(validate_qa_plan, self.ctx.spec_dir, self.docs_path)
        notes = validation.notes
        if overran:
            notes = f"{overran}\n\n{notes}".strip()
        loop = loop.update(plan_validation_notes=_finding(validation.status == "passed", notes))
        if validation.status != "passed":
            return self._guard_plan_validation(validation, loop)
        if dry_run:
            gate = self.call(verify_qa_dry_run, self.ctx.spec_dir, dry_run)
            if gate.status != "passed":
                self.logger.info(
                    "the QA plan did not dry-run clean — repairing again without "
                    "spending a suite run",
                    extra={"activity": True},
                )
                return self._guard_dry_run(
                    gate, loop.update(plan_validation_notes=_finding(False, gate.notes))
                )
        return Continue(validation, self.run, loop=loop)


    def stack(self, loop: QaLoop) -> Continue | Await | Done:
        """Bring the durable QA stack up, or send its manifest to the repair loop."""
        status = self.call(ensure_stack, self.docs_path)
        if status.ready == "unneeded":
            self.logger.info(
                "the book serves nothing — an empty stack is its topology, QA proceeds"
            )
            return Continue(status, self.plan, loop=loop)
        if status.ready == "none":
            self.logger.info(
                "the book serves a surface but declares no stack — routing to the setup fixer"
            )
            return self._guard_setup(
                status,
                loop.with_qa(QaResult(status="blocked", notes=status.notes)).update(
                    blocked_problems=()
                ),
            )
        if status.ready == "no":
            self.logger.info("QA stack did not come up: %s", status.failed_step)
            return self._guard_setup(
                status,
                loop.with_qa(QaResult(status="blocked", notes=status.notes)).update(
                    blocked_problems=()
                ),
            )
        return Continue(status, self.plan, loop=loop)

    def run(self, loop: QaLoop) -> Continue | Done:
        """Execute the plan through ostler's runner — the expensive step, and its own state."""
        self.logger.info("running the QA plan", extra={"activity": True})
        result = self.call(run_qa_plan, self.ctx.spec_dir, self.docs_path)
        loop = loop.with_qa(result).update(blocked_problems=_blocked_problems(result))
        if result.status == "passed":
            self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
            return Continue(result, self.verify_evidence, loop=loop)
        if self.stop_at_first_verdict and result.status == "failed":
            self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
            return self._first_verdict_ends(loop)
        return Continue(result, self.assess, loop=loop)

    def assess(self, loop: QaLoop) -> Continue | Await | Done:
        """Read the runner's verdict for what it means — four chained decisions, one state."""
        started = time.monotonic()
        turn = roles.turn(self, "qa-story", returns=QaAssessment)
        assessment = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="medium",
            session=backbone(self),
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
                "runner_status": loop.qa.status,
                "runner_notes": loop.qa.notes,
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if assessment.blocked:
            return self._refused(assessment, loop.charged(time.monotonic() - started),
                                 "the QA run assessment")
        loop = loop.charged(time.monotonic() - started).update(
            assessment=AssessmentRecord(
                notes=_finding(assessment.disposition == "confirmed", assessment.notes),
                disposition=assessment.disposition or "",
                failure_class=assessment.failure_class or "",
            ),
        )

        if self.stop_at_first_verdict:
            if (
                assessment.disposition == "repair_setup"
                or loop.qa.status == "blocked"
                or assessment.failure_class == "environment"
            ):
                return self._guard_setup(assessment, loop)
            return self._first_verdict_ends(loop)

        if assessment.disposition == "repair_setup":
            return self._guard_setup(assessment, loop)
        if assessment.disposition != "confirmed":
            elsewhere = self._routed(assessment, loop, assessment.findings, assessment.notes)
            if elsewhere is not None:
                return elsewhere
            return self._guard_plan(assessment, loop)

        if loop.qa.status == "blocked":
            return self._guard_setup(assessment, loop)
        if loop.qa.status not in {"passed", "failed"}:
            return self._guard_plan(assessment, loop)

        if assessment.failure_class == "product":
            failed = QaResult(
                status="failed",
                notes=assessment.notes or "QA assessment found a product defect.",
            )
            return Continue(assessment, self.backlog, loop=loop.with_qa(failed))
        if assessment.failure_class == "environment":
            return self._guard_setup(assessment, loop)
        if assessment.failure_class != "none":
            return self._guard_plan(assessment, loop)

        if not assessment.objective_reached:
            return self._guard_plan(assessment, loop)

        if loop.qa.status == "passed":
            return Continue(assessment, self.verify_evidence, loop=loop)
        return Continue(assessment, self.backlog, loop=loop)


    def verify_evidence(self, loop: QaLoop) -> Continue | Await | Done:
        """Fail closed: is the claimed pass backed by artifacts that exist on disk?"""
        result = self.call(
            verify_qa_evidence, self.ctx.spec_dir, loop.qa.status, loop.qa.notes
        )
        loop = loop.with_qa(result)
        if result.status == "passed":
            if self.stop_at_first_verdict:
                return Continue(result, self.finalize, loop=loop)
            return Continue(result, self.audit, loop=loop)
        if self.stop_at_first_verdict:
            return self._first_verdict_ends(loop)
        if result.status in {"failed", "blocked"}:
            return Continue(result, self.backlog, loop=loop)
        return self._guard_plan(result, loop)

    def audit(self, loop: QaLoop) -> Continue | Await | Done:
        """Try to refute the pass — `decide_qa_audit` and its two follow-on branches."""
        started = time.monotonic()
        turn = roles.turn(self, "audit-qa", returns=QaAudit)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_status": loop.qa.status,
                "qa_notes": loop.qa.notes,
            },
        )
        if result.blocked:
            return self._refused(result, loop.charged(time.monotonic() - started),
                                 "the QA audit")
        loop = loop.charged(time.monotonic() - started).update(
            audit=AuditRecord(
                notes=_finding(
                    result.verdict == "stands" and result.refutation_class == "none",
                    result.notes,
                ),
                verdict=result.verdict or "",
                refutation_class=result.refutation_class or "",
            ),
        )
        if result.verdict == "stands" and result.refutation_class == "none":
            return Continue(result, self.backlog, loop=loop)
        if result.verdict == "refuted" and result.refutation_class == "product-contradiction":
            failed = QaResult(
                status="failed",
                notes=result.notes or "QA audit found a product contradiction.",
            )
            return Continue(result, self.backlog, loop=loop.with_qa(failed))
        loop = loop.update(audit_rework=loop.audit_rework + 1)
        elsewhere = self._routed(result, loop, result.findings, result.notes)
        if elsewhere is not None:
            return elsewhere
        if loop.audit_rework > MAX_BLOCKING_AUDITS:
            self.logger.info(
                "the audit has refuted this pass %d times with plan-only findings — filing "
                "this one as backlog work rather than spending another plan repair",
                loop.audit_rework,
                extra={"activity": True},
            )
            return Continue(result, self.backlog, loop=loop)
        _note_lane_budget(loop, self.logger)
        return self._guard_plan(result, loop)


    def backlog(self, loop: QaLoop) -> Continue | Await | Done:
        """Drain separate-scope discoveries back to the author, then route on the verdict."""
        self.call(file_backlog_items, self.ctx.spec_dir, self.docs_path)
        if loop.qa.status == "passed":
            return Continue(loop.qa, self.feedback, loop=loop)
        if loop.qa.status == "failed":
            return Continue(loop.qa, self.triage, loop=loop)
        if loop.qa.status == "invalid":
            return self._guard_plan(loop.qa, loop)
        if loop.qa.status == "blocked":
            return self._guard_setup(loop.qa, loop)
        return self._fixable(loop.qa, loop)

    def triage(self, loop: QaLoop) -> Continue | Await | Done:
        """Classify the findings: fix them in-AC here, or hand the scope back to the author."""
        started = time.monotonic()
        turn = roles.turn(self, "triage-qa", returns=QaTriage)
        triage = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="medium",
            session=backbone(self),
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.qa.notes,
                "triage_scope": loop.triage_scope,
                "max_triage_scopes": str(MAX_TRIAGE_SCOPES),
            },
        )
        if triage.blocked:
            return self._refused(triage, loop.charged(time.monotonic() - started),
                                 "the QA triage")
        loop = loop.charged(time.monotonic() - started).update(
            failure_class=triage.qa_failure_class or ""
        )
        if loop.triage_scope >= MAX_TRIAGE_SCOPES:
            return self._fixable(triage, loop)
        if triage.triage_action == "rescope":
            self.logger.info("triage rescoped the story — handing back to dev")
            return self._ends(
                QaFlowResult(
                    status="rescope",
                    qa=loop.qa,
                    qa_rework=loop.qa_rework,
                    triage_scope=loop.triage_scope + 1,
                    docs_recheck_required=True,
                )
            )
        return self._fixable(triage, loop)

    def report_dev(self, loop: QaLoop) -> Await | Done:
        """`target_env=dev`: we do not own the code, so write the findings out and stop."""
        turn = roles.turn(self, "report-qa-dev", returns=QaReport)
        report = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="low",
            session=backbone(self),
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.qa.notes,
            },
        )
        if report.blocked:
            return self._blocked_report(report, loop, self.report_dev)
        self.logger.info("QA findings reported: %s", report.notes)
        return self._ends(
            QaFlowResult(
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )


    def feedback(self, loop: QaLoop) -> Continue:
        """Poll the run's inbox once before believing the pass."""
        note = self.call(check_feedback, str(self.run_dir))
        if note.present:
            self.logger.info("operator feedback found — re-QA after applying it")
            return Continue(note, self.apply_feedback, loop=loop, content=note.content)
        return Continue(note, self.regression, loop=loop)

    def apply_feedback(self, loop: QaLoop, content: str) -> Continue:
        """Apply the operator's note and rebuild the context — product feedback moves it."""
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes="",
            operator_feedback=content,
            power="low",
            session=f"qa-feedback:{self.ctx.story_slug}",
        )
        return Continue(
            result,
            self.build_context,
            loop=loop.charged(time.monotonic() - started)
            .require_docs_recheck()
            .with_qa(result),
        )

    def regression(self, loop: QaLoop) -> Continue:
        """Which committed journey suites, if any, this plan put at risk."""
        suites = self.call(detect_regression_suites, self.ctx.spec_dir)
        if suites.suites:
            return Continue(suites, self.run_regression, loop=loop)
        return Continue(suites, self.finalize, loop=loop)

    def run_regression(self, loop: QaLoop) -> Continue | Await | Done:
        """Run the committed suites, and decide what a green run means given what preceded it."""
        suites = self.output(detect_regression_suites)
        run = self.call(
            run_regression_suite,
            self.ctx.spec_dir,
            self.ctx.qa_dir,
            [suite.model_dump() for suite in suites.suites],
        )
        loop = loop.with_qa(run.as_qa_result())
        if run.status in {"passed", "skipped"}:
            if loop.regression_fix_applied:
                return Continue(
                    run,
                    self.build_context,
                    loop=loop.update(regression_fix_applied=False, regression_reqa_pending=True),
                )
            return Continue(
                run,
                self.finalize,
                loop=loop.update(regression_fix_applied=False, regression_reqa_pending=False),
            )
        if run.status in {"blocked", "error"}:
            return self._guard_setup(
                run,
                loop.update(regression_fix_applied=False, regression_reqa_pending=True),
            )
        if loop.regression_fix >= MAX_REGRESSION_FIXES:
            unresolved = QaResult(
                status="failed",
                notes=(
                    f"Regression suite still failing after {loop.regression_fix} fix "
                    f"attempt(s): {run.notes or 'no failure detail captured'}"
                ),
            )
            return self._guard_qa(
                run,
                loop.update(
                    qa=unresolved,
                    regression_fix_applied=False,
                    regression_reqa_pending=False,
                ),
            )
        return Continue(
            run,
            self.fix_regression,
            loop=loop.update(regression_fix_applied=False, regression_reqa_pending=False),
        )

    def fix_regression(self, loop: QaLoop) -> Continue | Await | Done:
        """Reproduce and fix a real-stack journey failure, then run the suite again."""
        suites = self.output(detect_regression_suites)
        run = self.output(run_regression_suite)
        self.logger.info("fixing the regression suite", extra={"activity": True})
        started = time.monotonic()
        turn = roles.turn(self, "fix-regression", returns=RegressionFix)
        fix = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=5400,
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "regression_suites": [
                    f"{suite.label}: {suite.command}" for suite in suites.suites
                ],
                "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
                "regression_run_status": run.status,
                "regression_run_failing_tests": run.failing_tests,
                "regression_run_notes": run.notes,
                "regression_run_log_path": run.log_path,
                "regression_fix_count": loop.regression_fix,
            },
            session=f"qa-regression-fix:{self.ctx.story_slug}",
        )
        loop = loop.charged(time.monotonic() - started)
        if fix.blocked:
            return self._refused(fix, loop, "the regression fixer")
        return Continue(
            run,
            self.run_regression,
            loop=loop.update(
                regression_fix=loop.regression_fix + 1,
                regression_fix_applied=True,
                docs_recheck_required=True,
            ),
        )

    def finalize(self, loop: QaLoop) -> Continue | Await | Done:
        """The two pre-commit hygiene gates, and the only path to a passing story."""
        self.call(flush_root_screenshots, self.ctx.spec_dir)
        result = self.call(check_sentinel_ids, self.ctx.story_slug)
        loop = loop.with_qa(result)
        if result.status != "passed":
            if self.stop_at_first_verdict:
                return self._first_verdict_ends(loop)
            return self._guard_qa(result, loop)
        if self.target_env == "dev":
            return Continue(result, self.report_dev_pass, loop=loop)
        self.logger.info("QA passed for %s", self.ctx.story_slug)
        return self._ends(
            QaFlowResult(
                status="passed",
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    def report_dev_pass(self, loop: QaLoop) -> Await | Done:
        """`target_env=dev`: summarise what passed to the tracker, then finish green."""
        turn = roles.turn(self, "report-qa-dev-pass", returns=QaReport)
        report = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="low",
            session=backbone(self),
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.block_notes,
            },
        )
        if report.blocked:
            return self._blocked_report(report, loop, self.report_dev_pass)
        return self._ends(
            QaFlowResult(
                status="passed",
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )


    def apply_fixes(self, loop: QaLoop) -> Continue | Await:
        """Fix what QA found, spend a rework, and re-derive the context before re-planning."""
        failed = _failed_scenarios(self)
        if failed:
            self.logger.info(
                "splitting the fix pass into %d per-scenario item(s): %s",
                len(failed),
                ", ".join(failed),
                extra={"activity": True},
            )
            return Continue(
                loop.qa,
                self.fix_item,
                loop=loop.update(
                    qa_rework=loop.qa_rework + 1,
                    docs_recheck_required=True,
                    fix=FixWorklist(items=failed),
                ),
            )
        self.logger.info("applying QA fixes", extra={"activity": True})
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes=loop.qa.notes,
            operator_feedback=None,
            power="high",
            session=backbone(self),
        )
        loop = loop.charged(time.monotonic() - started).update(
            qa=result, qa_rework=loop.qa_rework + 1, docs_recheck_required=True
        )
        if result.blocked:
            self.logger.info("QA fixer reported blocked; escalating: %s", result.notes)
            return self._gate(result, loop)
        return Continue(result, self.build_context, loop=loop)

    def fix_item(self, loop: QaLoop) -> Continue | Await | Done:
        """Fix the scenario at the head of the worklist, and prove it before taking the next."""
        if not loop.fix.items:
            return Continue(loop.qa, self.build_context, loop=loop)
        item = loop.fix.items[0]
        self.logger.info(
            "fixing QA scenario %s (%d left, attempt %d)",
            item,
            len(loop.fix.items),
            loop.fix.rework + 1,
            extra={"activity": True},
        )
        started = time.monotonic()
        result = self._fix_scenario(item, loop)
        loop = loop.charged(time.monotonic() - started)
        if result.blocked:
            self.logger.info("scenario fixer reported blocked; escalating: %s", result.notes)
            return self._gate(result, loop.update(qa=result))
        gate = self.call(verify_qa_dry_run, self.ctx.spec_dir, (item,))
        if gate.status == "passed":
            self.logger.info("scenario %s is green in its dry run", item)
            return self._next_item(result, loop)
        problem = f"{item}: {gate.notes}"
        loop = loop.update(
            fix=loop.fix.model_copy(update={"problems": (*loop.fix.problems, problem)})
        )
        if problem in loop.fix.problems[:-1]:
            self.logger.info(
                "scenario %s was refused for the identical reason twice; escalating: %s",
                item,
                gate.notes,
            )
            return self._gate(gate, loop.update(qa=result))
        loop = loop.update(fix=loop.fix.model_copy(update={"rework": loop.fix.rework + 1}))
        if loop.fix.rework >= MAX_FIX_ITEM_REWORKS:
            self.logger.info(
                "scenario %s has had its %d attempts; carrying it into the scored run as "
                "written and letting that run judge it",
                item,
                loop.fix.rework,
            )
            return self._next_item(result, loop)
        return Continue(result, self.fix_item, loop=loop)

    def _next_item(self, result: QaResult, loop: QaLoop) -> Continue | Await | Done:
        """Pop the head of the worklist: the next scenario, or the scored re-run."""
        rest = loop.fix.items[1:]
        loop = loop.update(fix=loop.fix.popped())
        if rest:
            return Continue(result, self.fix_item, loop=loop)
        return Continue(result, self.build_context, loop=loop.update(qa=result))

    def _fix_scenario(self, item: str, loop: QaLoop) -> QaResult:
        """`fix-qa-scenario.md`: one scenario's brief, its assertions and its dry-run contract."""
        spec_abs = Path(self.ctx.spec_dir) if self.ctx.spec_dir else None
        failed_assertions = (
            qa_support.failed_assertions(qa_support.scored_run_log(spec_abs)) if spec_abs else {}
        )
        turn = roles.turn(self, "fix-qa-scenario", returns=QaRunResult)
        reported = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="low",
            add_dirs=self._dirs(),
            args=turn.args
            | {
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "qa_dir": self.ctx.qa_dir,
                "qa_scratch_dir": QA_SCRATCH_DIRNAME,
                "scenario": item,
                "failed_assertions": failed_assertions.get(item, []),
                "remaining_scenarios": list(loop.fix.items[1:]),
                "qa_notes": loop.qa.notes,
            },
            session=backbone(self),
        )
        return QaResult(status=reported.status, notes=reported.notes)


    def setup_fix(self, loop: QaLoop) -> Continue | Await | Done:
        """Repair the runbook that would not come up — or write the one nobody wrote."""
        self.logger.info("repairing the QA stack", extra={"activity": True})
        impl = self.output(resolve_impl_context)
        started = time.monotonic()
        turn = roles.turn(self, "setup-fix", returns=SetupResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=2400,
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.block_notes,
                "qa_run_plan": impl.qa_run_plan,
                "verification_setup": impl.verification_setup,
                "fixtures": [f.model_dump() for f in impl.fixtures],
                "runtime_python": sys.executable,
            },
        )
        loop = loop.charged(time.monotonic() - started).update(
            setup_rework=loop.setup_rework + 1,
            docs_recheck_required=True,
            setup_problems=loop.blocked_problems,
        )
        if result.blocked:
            return self._gate(result, loop)
        return Continue(result, self.stack, loop=loop)


    def resolve_operator(self, loop: QaLoop) -> Continue | Await:
        """Resolve a QA block from what is already written down, or park the run for a human."""
        self.logger.info("diagnosing the QA block for the operator", extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args={
                **resolver_args(
                self, block_kind="qa", notes=loop.block_notes, docs_path=self.docs_path
            ),
                "qa_dir": self.ctx.qa_dir,
            },
        )
        if answered(self, result, "qa"):
            return Continue(result, self.read_operator, loop=loop)
        gate = _escalation(self, loop, result)
        return Await(context_path(self), gate.body, self.read_operator, loop=loop)

    def read_operator(self, loop: QaLoop) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the block to the epic — handing back to replan")
            return self._ends(
                QaFlowResult(
                    status="replan",
                    qa=loop.qa,
                    qa_rework=loop.qa_rework,
                    triage_scope=loop.triage_scope,
                    operator_notes=answer.content,
                    docs_recheck_required=loop.docs_recheck_required,
                )
            )
        return Continue(answer, self.apply_resolved, loop=loop, content=answer.content)

    def apply_resolved(self, loop: QaLoop, content: str) -> Continue | Await:
        """Apply the operator's answer as a QA fix, and spend a rework on it."""
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes=loop.qa.notes,
            operator_feedback=content,
            power="low",
            session=backbone(self),
        )
        loop = loop.charged(time.monotonic() - started).update(
            qa=result,
            qa_rework=loop.qa_rework + 1,
            docs_recheck_required=True,
        )
        if result.blocked:
            return self._refused(result, loop, "the operator-guided QA fix")
        if loop.qa_rework >= MAX_QA_REWORKS:
            self.logger.info("operator-guided rework loop is out of QA reworks — escalating")
            return self._exhausted(loop, f"{loop.qa_rework} operator-guided rework")
        return Continue(result, self.build_context, loop=loop)


    def _routed(
        self,
        result: object,
        loop: QaLoop,
        findings: Sequence[QaFinding],
        notes: str,
    ) -> Continue | Await | Done | None:
        """Send a gate's findings to whoever can repair them."""
        routed = _route_findings(findings)
        if routed.product_test:
            self.logger.info(
                "routing %d QA finding(s) to the fix loop — their repair is in the product, "
                "not the plan", len(routed.product_test),
                extra={"activity": True},
            )
            brief = _brief(routed.product_test, notes)
            return self._fixable(
                result, loop.update(qa=loop.qa.model_copy(update={"notes": brief}))
            )
        if routed.plan:
            return None
        if routed.stack:
            self.logger.info(
                "routing %d QA finding(s) to the setup loop — the stack manifest is "
                "`ensure_stack`'s", len(routed.stack),
                extra={"activity": True},
            )
            brief = _brief(routed.stack, notes)
            return self._guard_setup(
                result, loop.update(qa=loop.qa.model_copy(update={"notes": brief}))
            )
        return None

    def _guard_plan(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Spend the post-run component of the QA-plan judgement budget."""
        if _repeating(loop, "QA-plan repair", _run_failures(self)):
            return self._stalled(result, loop, "QA-plan repair")
        if loop.plan_judgement_rework >= MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return self._plan_lap(
            result,
            loop.with_lap(
                "QA-plan repair",
                plan_rework=loop.plan_rework + 1,
                repaired_failures=_run_failures(self),
            ),
        )

    def _guard_dry_run(self, gate: object, loop: QaLoop) -> Continue | Await | Done:
        """A repair whose own dry run refused it — repair again, on the same budget."""
        stalled = self._rejected(gate, loop, "dry-run refusal")
        if stalled is not None:
            return stalled
        loop = self._recorded(loop, "dry-run refusal")
        if loop.plan_judgement_rework >= MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return self._plan_lap(
            gate,
            loop.with_lap(
                "QA-plan repair",
                plan_rework=loop.plan_rework + 1,
                repaired_failures=_run_failures(self),
            ),
        )

    def _recorded(self, loop: QaLoop, kind: str) -> QaLoop:
        """The same loop, remembering that the plan lane was sent back on this."""
        return loop.update(plan_rejections=(*loop.plan_rejections, _rejection(loop, kind)))

    def _rejected(self, gate: object, loop: QaLoop, kind: str) -> Continue | Await | None:
        """Escalate a pre-run rejection the plan lane has already answered once."""
        problem = _rejection(loop, kind)
        if problem not in loop.plan_rejections:
            return None
        self.logger.info(
            "the QA plan was refused for the identical reason twice (%s) — escalating "
            "instead of spending another lap",
            kind,
            extra={"activity": True},
        )
        self.logger.info("stall reason: a QA-plan repair that answered nothing the gate reads")
        return self._gate(gate, loop)

    def _stalled(self, result: object, loop: QaLoop, lap: str) -> Continue | Await | Done:
        """A repair loop that has stopped moving — escalate rather than spend the budget."""
        other = "code fix" if lap == "QA-plan repair" else "QA-plan repair"
        if not loop.class_switched and other not in loop.tried_laps:
            return self._switched(result, loop, lap, other)
        self.logger.info(
            "the last %s left the QA run failing identically (%s) — escalating instead of "
            "spending another lap",
            lap,
            "; ".join(_run_failures(self)),
            extra={"activity": True},
        )
        self.logger.info(
            "stall reason: a %s that changed nothing%s",
            lap,
            " after switching repair class" if loop.class_switched else "",
        )
        return self._gate(result, loop)

    def _switched(
        self, result: object, loop: QaLoop, spent: str, other: str
    ) -> Continue | Await | Done:
        """A repair that moved nothing refutes the *hypothesis*, not the story."""
        self.logger.info(
            "the %s left the QA run failing identically (%s) — trying a %s before the "
            "operator, because a repair that moved nothing refutes the hypothesis class",
            spent,
            "; ".join(_run_failures(self)),
            other,
            extra={"activity": True},
        )
        loop = loop.update(
            class_switched=True,
            qa=loop.qa.model_copy(update={"notes": _SWITCHED.format(spent=spent)}),
        )
        if other == "code fix":
            return self._fixable(result, loop)
        return self._guard_plan(result, loop)

    def _guard_plan_validation(
        self, result: object, loop: QaLoop
    ) -> Continue | Await | Done:
        """Spend a schema-validation repair — a budget of its own, not the judgement one."""
        stalled = self._rejected(result, loop, "QA-plan schema refusal")
        if stalled is not None:
            return stalled
        loop = self._recorded(loop, "QA-plan schema refusal")
        if loop.plan_validation_rework >= MAX_PLAN_VALIDATION_REWORKS:
            return self._exhausted(
                loop, f"{loop.plan_validation_rework} QA-plan schema repair"
            )
        return self._plan_lap(
            result,
            loop.update(plan_validation_rework=loop.plan_validation_rework + 1),
        )

    def _plan_lap(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Take the lap the guard just paid for, unless the plan has had too many in total."""
        _note_plan_budget(loop, self.logger)
        if loop.plan_rework_total > MAX_TOTAL_PLAN_LAPS:
            self.logger.info(
                "the QA plan has had %d repair laps across every gate — ending the flow",
                loop.plan_rework_total - 1,
            )
            return self._exhausted(loop, f"{loop.plan_rework_total - 1} total QA-plan lap")
        return Continue(result, self.repair_plan, loop=loop)

    def _guard_setup(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_setup`: another repair attempt, or the operator gate."""
        if loop.setup_rework >= MAX_SETUP_REWORKS:
            return self._exhausted(loop, f"{loop.setup_rework} QA-setup repair")
        _note_lane_budget(loop, self.logger)
        if loop.blocked_problems and loop.blocked_problems == loop.setup_problems:
            self.logger.info(
                "the QA setup fix left the identical blocked bundle (%s) — escalating",
                "; ".join(loop.blocked_problems),
                extra={"activity": True},
            )
            return self._gate(result, loop)
        return Continue(result, self.setup_fix, loop=loop)

    def _guard_qa(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_qa` + `guard_qa_bonus` + `decide_bonus_class` + `grant_qa_bonus`."""
        if _repeating(loop, "code fix", _run_failures(self)):
            return self._stalled(result, loop, "code fix")
        loop = loop.with_lap("code fix", repaired_failures=_run_failures(self))
        _note_lane_budget(loop, self.logger)
        if loop.qa_rework < MAX_QA_REWORKS:
            return Continue(result, self.apply_fixes, loop=loop)
        if loop.bonus_used or loop.failure_class != "evidence":
            return self._exhausted(loop, f"{loop.qa_rework} code rework")
        self.logger.info("granting the one verification-only bonus pass")
        return Continue(result, self.apply_fixes, loop=loop.update(bonus_used=True))

    def _fixable(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`decide_qa_fixable`: in a `dev` run the findings are reported, not fixed."""
        if self.target_env == "dev":
            return Continue(result, self.report_dev, loop=loop)
        if loop.failure_class == "product" and loop.triage_scope < MAX_TRIAGE_SCOPES:
            self.logger.info(
                "triage called this a product failure — returning the story to the dev lane",
                extra={"activity": True},
            )
            return self._ends(
                QaFlowResult(
                    status="refix",
                    qa=loop.qa,
                    qa_rework=loop.qa_rework,
                    triage_scope=loop.triage_scope + 1,
                    docs_recheck_required=True,
                )
            )
        return self._guard_qa(result, loop)

    def _refused(self, result: object, loop: QaLoop, what: str) -> Continue | Await:
        """A turn that said it cannot get there, handed straight to the operator."""
        reason = getattr(result, "notes", "") or "no reason given"
        self.logger.info("%s reported it cannot proceed; escalating: %s", what, reason)
        loop = loop.update(
            qa=loop.qa.model_copy(update={"notes": f"{what} reported it cannot proceed: {reason}"})
        )
        return self._gate(result, loop)

    def _blocked_report(
        self, report: QaReport, loop: QaLoop, resume: _ReportState
    ) -> Await:
        """A report turn that could not write its summary parks the story on the operator."""
        reason = report.notes or "no reason given"
        self.logger.info("the QA report could not be written; escalating: %s", reason)
        loop = loop.update(
            escalations=loop.escalations + 1,
            qa=loop.qa.model_copy(
                update={"notes": f"the QA report could not be written: {reason}"}
            ),
        )
        gate = _escalation(self, loop)
        return Await(context_path(self), gate.body, resume, loop=loop)

    def _gate(self, result: object, loop: QaLoop) -> Continue | Await:
        """`gate_qa`: hand the block to the auto-operator, or halt for a human."""
        loop = loop.update(escalations=loop.escalations + 1)
        if self.operator_mode in {"human", "operator"} or loop.escalations > MAX_QA_BLOCKS:
            gate = _escalation(self, loop)
            return Await(context_path(self), gate.body, self.read_operator, loop=loop)
        return Continue(result, self.resolve_operator, loop=loop)

    def _exhausted(self, loop: QaLoop, spent: str = "") -> Continue | Await:
        """Out of budget — hand the block to the operator gate."""
        if spent:
            self.logger.info("QA budget exhausted (%s) — escalating", spent)
        return self._gate(loop, loop)

    def _apply_fixes(
        self, *, qa_notes: str, operator_feedback: str | None, power: str, session: str
    ) -> QaResult:
        """`apply-qa-fixes.md`, rendered by three callers with three different argument sets."""
        args: dict[str, object] = {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id or self.ctx.story_slug,
            "epic": self.epic,
            "qa_dir": self.ctx.qa_dir,
            "qa_notes": qa_notes,
        }
        if operator_feedback is not None:
            args["operator_feedback"] = operator_feedback
        turn = roles.turn(self, "apply-qa-fixes", returns=QaRunResult)
        reported = self.agent(
            turn.prompt,
            returns=turn.returns,
            power=power,
            add_dirs=self._dirs(),
            args=turn.args | args,
            session=session,
        )
        return QaResult(status=reported.status, notes=reported.notes)

    def _dirs(self) -> list[str]:
        """The repos this story's plan touches — every agent turn's `add_dirs`."""
        return list(self.output(resolve_impl_context).affected_repo_paths)


__all__ = ["Qa"]
