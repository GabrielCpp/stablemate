"""The rubric survey as a state machine — the port of `author/workflow.yaml`'s `flows.surveyor` (51 nodes, lines 1560-2116)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import (
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.author.shared.survey.inventory import expand_inventory, split_unit
from workhorse_workflows.author.shared.survey.records import validate_record, verify_records
from workhorse_workflows.author.shared.survey.units import mark_unit, select_next_unit
from workhorse_workflows.author.surveyor.nodes import (
    check_inventory,
    emit_artifacts,
    load_survey_config,
    validate_partition,
)
from workhorse_workflows.author.shared.schemas import (
    OperatorResolution,
    PartitionProposal,
    PlanResult,
    RecordFix,
    SurveyConfig,
    UnitAssessment,
)
from workhorse_workflows.kit.telemetry import counter_labels

MAX_PLAN_REWORKS = 2
MAX_PLAN_RESOLVES = 2
MAX_RECORD_FIXES = 2
MAX_PARTITION_REWORKS = 3
MAX_PARTITION_RESOLVES = 2
MAX_VERIFY_RESOLVES = 2
UNBOUNDED = float("inf")


class Surveyor(Workflow):
    """Survey a repo against one rubric, exhaustively, one unit at a time."""

    rubric: str = "docs/survey/rubric.md"
    survey_dir: str = "docs/survey"
    operator_mode: str = "auto"

    def setup(self) -> SurveyConfig:
        """Resolve the survey's paths and prove the rubric exists."""
        return self.call(
            load_survey_config, self.rubric, self.survey_dir
        )

    def labels(self) -> dict[str, str]:
        """Which unit the survey is on, and how far along — the YAML's `labels:` block."""
        try:
            pick = self.output(select_next_unit)
        except NodeNotRunError:
            return {}
        return {"work_id": pick.unit_id, "progress": pick.progress}

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = (
        "plan_rework",
        "plan_resolve",
        "record_fix",
        "verify_resolve",
        "partition_rework",
        "partition_resolve",
    )

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The work labels plus the bounded attempt counters carried by this state."""
        return self.labels() | counter_labels(params, "surveyor", self.BUDGET_LABELS)

    @property
    def _context(self) -> Path:
        """The operator context file, absolute — what an `Await` writes its ask to."""
        return Path(self.ctx.repo_root) / self.ctx.context


    def start(self) -> Continue:
        """Decide whether the granularity planner needs to run at all."""
        check = self.call(check_inventory, self.ctx.inventory, self.ctx.rules)
        if check.needs_plan:
            return Continue(check, self.plan)
        return Continue(check, self.expand)

    def plan(
        self, plan_rework: int = 0, plan_errors: str = "", plan_resolve: int = 0
    ) -> Continue | Await:
        """One bounded judgment: what a unit *is* for this rubric, in this repo."""
        result = self.agent(
            "surveyor/prompts/plan-units.md",
            returns=PlanResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "rubric": self.ctx.rubric,
                "rules_path": self.ctx.rules,
                "survey_dir": self.ctx.survey_dir,
                "context_path": self.ctx.context,
                "plan_errors": plan_errors,
            },
        )
        if result.status == "blocked":
            return self._gate_plan(result, result.notes or plan_errors, plan_resolve)
        return Continue(
            result,
            self.expand,
            plan_rework=plan_rework,
            plan_resolve=plan_resolve,
        )

    def expand(self, plan_rework: int = 0, plan_resolve: int = 0) -> Continue | Await:
        """Materialize the frozen unit list from the rules — or consume the frozen one."""
        expansion = self.call(expand_inventory, self.ctx.rules, self.ctx.inventory)
        if expansion.expand_ok:
            return Continue(expansion, self.pick)
        if plan_rework >= MAX_PLAN_REWORKS:
            return self._gate_plan(expansion, expansion.expand_errors, plan_resolve)
        return Continue(
            expansion,
            self.plan,
            plan_rework=plan_rework + 1,
            plan_errors=expansion.expand_errors,
            plan_resolve=plan_resolve,
        )

    def _gate_plan(
        self, result: object, notes: str, plan_resolve: int
    ) -> Continue | Await:
        """`gate_plan`: hand the granularity block to the resolver, or to the human."""
        if self.operator_mode == "human" or plan_resolve >= MAX_PLAN_RESOLVES:
            return Await(
                self._context,
                notes,
                self.plan,
                plan_rework=0,
                plan_resolve=plan_resolve,
            )
        return Continue(result, self.resolve_plan, notes=notes, plan_resolve=plan_resolve)

    def resolve_plan(self, notes: str, plan_resolve: int = 0) -> Await:
        """Investigate a granularity block, then park for the operator."""
        self.logger.info("resolving the granularity block", extra={"activity": True})
        self.agent(
            "surveyor/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self.ctx.context,
                "survey_dir": self.ctx.survey_dir,
                "block_stage": "plan-units",
                "block_notes": notes,
            },
        )
        return Await(
            self._context,
            notes,
            self.plan,
            plan_rework=0,
            plan_resolve=plan_resolve + 1,
        )


    def pick(self, verify_resolve: int = 0) -> Continue:
        """Take the next pending unit, or fall through to the coverage gate."""
        pick = self.call(select_next_unit, self.ctx.inventory, self.ctx.findings_dir)
        if not pick.has_unit:
            return Continue(pick, self.verify, verify_resolve=verify_resolve)
        return Continue(
            pick,
            self.assess,
            unit_id=pick.unit_id,
            unit_path=pick.unit_path,
            unit_kind=pick.unit_kind,
            record_path=pick.record_path,
            progress=pick.progress,
            verify_resolve=verify_resolve,
        )

    def assess(
        self,
        unit_id: str,
        unit_path: str,
        unit_kind: str,
        record_path: str,
        progress: str = "",
        verify_resolve: int = 0,
    ) -> Continue:
        """Assess one unit against the rubric and write its finding record."""
        self.logger.info(
            "assessing %s %s%s",
            unit_kind,
            unit_id,
            f" · {progress}" if progress else "",
            extra={"activity": True},
        )
        result = self.agent(
            "surveyor/prompts/assess-unit.md",
            returns=UnitAssessment,
            power="medium",
            cwd=self.ctx.repo_root,
            args={
                "unit_id": unit_id,
                "unit_path": unit_path,
                "unit_kind": unit_kind,
                "record_path": record_path,
                "rubric": self.ctx.rubric,
                "context_path": self.ctx.context,
            },
        )
        if result.status == "split":
            return Continue(
                result,
                self.split,
                unit_id=unit_id,
                record_path=record_path,
                verify_resolve=verify_resolve,
            )
        return Continue(
            result,
            self.check,
            unit_id=unit_id,
            record_path=record_path,
            verify_resolve=verify_resolve,
        )

    def split(
        self, unit_id: str, record_path: str, verify_resolve: int = 0
    ) -> Continue:
        """Replace a too-big unit with its immediate children, or mark it and move on."""
        result = self.call(split_unit, self.ctx.inventory, unit_id)
        if result.split_ok:
            return Continue(result, self.pick, verify_resolve=verify_resolve)
        marked = self.call(
            mark_unit, self.ctx.inventory, unit_id, record_path, result.split_errors
        )
        return Continue(marked, self.pick, verify_resolve=verify_resolve)

    def check(
        self,
        unit_id: str,
        record_path: str,
        record_fix: int = 0,
        verify_resolve: int = 0,
    ) -> Continue:
        """Check the record the turn wrote, then take the unit off the pending list."""
        check = self.call(validate_record, record_path, unit_id)
        if check.record_ok:
            marked = self.call(mark_unit, self.ctx.inventory, unit_id, record_path)
            return Continue(marked, self.pick, verify_resolve=verify_resolve)
        if record_fix >= MAX_RECORD_FIXES:
            marked = self.call(
                mark_unit, self.ctx.inventory, unit_id, record_path, check.record_errors
            )
            return Continue(marked, self.pick, verify_resolve=verify_resolve)
        return Continue(
            check,
            self.fix,
            unit_id=unit_id,
            record_path=record_path,
            record_errors=check.record_errors,
            record_fix=record_fix,
            verify_resolve=verify_resolve,
        )

    def fix(
        self,
        unit_id: str,
        record_path: str,
        record_errors: str,
        record_fix: int = 0,
        verify_resolve: int = 0,
    ) -> Continue:
        """One bounded repair of an invalid record, then re-validate."""
        self.agent(
            "surveyor/prompts/fix-record.md",
            returns=RecordFix,
            power="medium",
            cwd=self.ctx.repo_root,
            args={
                "record_path": record_path,
                "unit_id": unit_id,
                "record_errors": record_errors,
            },
        )
        return Continue(
            None,
            self.check,
            unit_id=unit_id,
            record_path=record_path,
            record_fix=record_fix + 1,
            verify_resolve=verify_resolve,
        )


    def verify(self, verify_resolve: int = 0) -> Continue | Await:
        """Every frozen unit accounted for, with a record, and no silent shrinkage."""
        result = self.call(verify_records, self.ctx.inventory, self.ctx.findings_dir)
        if result.holds:
            return Continue(result, self.partition)
        notes = result.verify_errors or result.verify_report
        if self.operator_mode == "human" or verify_resolve >= MAX_VERIFY_RESOLVES:
            return Await(self._context, notes, self.pick, verify_resolve=verify_resolve)
        return Continue(
            result, self.resolve_verify, notes=notes, verify_resolve=verify_resolve
        )

    def resolve_verify(self, notes: str, verify_resolve: int = 0) -> Await:
        """Investigate a coverage failure, then park for the operator."""
        self.logger.info("resolving the coverage block", extra={"activity": True})
        self.agent(
            "surveyor/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self.ctx.context,
                "survey_dir": self.ctx.survey_dir,
                "block_stage": "survey-coverage",
                "block_notes": notes,
            },
        )
        return Await(self._context, notes, self.pick, verify_resolve=verify_resolve + 1)


    def partition(
        self,
        partition_rework: int = 0,
        partition_errors: str = "",
        partition_resolve: int = 0,
    ) -> Continue | Await:
        """Cluster the findings into work items, losslessly."""
        result = self.agent(
            "surveyor/prompts/partition-findings.md",
            returns=PartitionProposal,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "findings_dir": self.ctx.findings_dir,
                "inventory": self.ctx.inventory,
                "partition_path": self.ctx.partition,
                "rubric": self.ctx.rubric,
                "context_path": self.ctx.context,
                "partition_errors": partition_errors,
            },
        )
        if result.status == "blocked":
            return self._gate_partition(
                result, result.notes or partition_errors, partition_resolve
            )
        check = self.call(validate_partition, self.ctx.partition, self.ctx.inventory)
        if check.partition_ok:
            return Continue(check, self.emit)
        if partition_rework >= MAX_PARTITION_REWORKS:
            return self._gate_partition(check, check.partition_errors, partition_resolve)
        return Continue(
            check,
            self.partition,
            partition_rework=partition_rework + 1,
            partition_errors=check.partition_errors,
            partition_resolve=partition_resolve,
        )

    def _gate_partition(
        self, result: object, notes: str, partition_resolve: int
    ) -> Continue | Await:
        """`gate_partition`: hand the clustering block to the resolver, or to the human."""
        if self.operator_mode == "human" or partition_resolve >= MAX_PARTITION_RESOLVES:
            return Await(
                self._context,
                notes,
                self.partition,
                partition_rework=0,
                partition_resolve=partition_resolve,
            )
        return Continue(
            result,
            self.resolve_partition,
            notes=notes,
            partition_resolve=partition_resolve,
        )

    def resolve_partition(self, notes: str, partition_resolve: int = 0) -> Await:
        """Investigate a clustering block, then park for the operator."""
        self.logger.info("resolving the partition block", extra={"activity": True})
        self.agent(
            "surveyor/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": self.ctx.context,
                "survey_dir": self.ctx.survey_dir,
                "block_stage": "partition",
                "block_notes": notes,
            },
        )
        return Await(
            self._context,
            notes,
            self.partition,
            partition_rework=0,
            partition_resolve=partition_resolve + 1,
        )

    def emit(self) -> Done:
        """Write the generated backlog bullets and the unit-level manifest."""
        result = self.call(
            emit_artifacts,
            self.ctx.partition,
            self.ctx.inventory,
            self.ctx.unit_manifest,
        )
        if not result.emit_ok:
            raise WorkflowFailed(
                f"survey emission failed: {result.emit_errors or result.emit_note}"
            )
        return Done(result)


__all__ = ["Surveyor"]
