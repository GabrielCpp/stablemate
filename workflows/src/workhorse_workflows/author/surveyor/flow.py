"""The rubric survey as a state machine — the port of `author/workflow.yaml`'s
`flows.surveyor` (51 nodes, lines 1560-2116).

It asks one question of a whole repo — *where does this cross-cutting concern apply, and
what does it imply here* — and it is a **survey**, so its contract is exhaustiveness: one
frozen unit per surface, one finding record per unit, and the empty pending set as the
proof. Between the two ends sits a per-unit loop:

    plan granularity → freeze the unit list
      → (pick → assess → validate → mark)*
      → verify coverage → partition findings → emit backlog + manifest

Fifty-one nodes become thirteen states. Almost everything that disappeared was one of
three shapes the YAML had no other way to write:

* **branches reading the node directly above them.** `decide_plan`, `decide_expand`,
  `decide_unit`, `decide_assess`, `decide_split`, `decide_record`, `decide_verify`,
  `decide_partition`, `decide_emit`, `decide_plan_result`, `decide_partition_agent`,
  `decide_verify_resolve` — twelve of them, every one an `if` written across two nodes
  because a script cannot route.
* **counters.** `reset_plan_rework` / `incr_plan` / `guard_plan` and its three siblings
  (record fixes, partition reworks, verify resolves) become state parameters: reset is a
  default argument, increment is `+ 1`, and the guard is the `if` that reads it. Cumulative
  `plan_resolve` and `partition_resolve` parameters additionally bound the autonomous cycles
  across those local resets. `init_counter.py` and `incr_counter.py` are not ported.
* **fan-in terminals.** `survey_failed` is a `type: fail` node reached from one branch;
  each site raises `WorkflowFailed` with the errors it actually saw, which is the one
  place this port says more than the YAML did — a shared fail node cannot name the gate
  that tripped it.

Divergences from the YAML, all deliberate:

* **the three operator gates never decide on the operator's behalf.** In the YAML,
  `resolve_plan` and `resolve_partition` route *unconditionally* into an
  `await-operator.py` node, and that script's own state machine could still decide the
  run continues: it read `STATUS:` from the context file, and `ANSWERED` (which the
  resolver wrote when it resolved the block itself) flipped to `CONSUMED` and returned
  immediately without a human. This port removes that: `resolve-operator.md` is
  diagnosis-only — it investigates and writes findings, it never decides the
  scope/granularity/clustering question or edits a file to resolve it — so all three
  resolvers (`resolve_plan`, `resolve_verify`, `resolve_partition`) unconditionally
  return `Await`. The `answered`/`escalated` split in `OperatorResolution` is a relic of
  the old auto-resolve contract kept for now because the coder side of the codebase
  still shares the field names; nothing here reads `.decision` any more.
* `await-operator.py`'s **append-and-re-arm** behavior is not reproduced: `Await` writes
  the questions to the context file, replacing it. So a second block overwrites the
  first block's questions and the answer to them. The prompts read the file for history
  (their own prior `## Your answers` section is their loop guard), so this is a real
  loss of the operator transcript — recorded as a finding for the deletion loop rather
  than fixed here, since the fix is in the driver and the driver API is not this port's
  to change.
* `verify_resolve` is threaded through **every** state of the per-unit loop, because in
  the YAML it is a workflow var that survives the loop and is read at the coverage gate
  on the way out. It is the only counter that does.
* `await_verify` does **not** reset its counter. The plan and partition awaits reset their
  local rework counters but preserve the cumulative resolver counters: once a run has burned
  two auto-resolutions at any of the three gates, every later failure there goes straight to
  the human.
* `decide_verify` routes only the literal `"no"` to the gate, so `verify_records`'
  third answer — `"skip"`, nothing was surveyed — *passes*. `VerifyResult` models that
  as `holds=True, nothing_surveyed=True`, so the gate here is plain `if not holds`. The
  parity flow's gate differs, and deliberately: see `parity_surveyor`.
* the agent nodes' `default:` outputs are dropped. Every one of them — `{status:
  complete}`, `{status: assessed}`, `{status: fixed}`, `{decision: answered}` — names
  the value that its branch's `default:` arm already selects, so the blank the models
  default to lands on the same arm. The one place the two differ is the operator gate,
  and there blank is the *safer* of the two (above).
* `refuel: unit_id` on `select_unit` has no counterpart: pyflow has no gas tank, and the
  transition budget bounds the machine instead. Left as the operator's
  `WORKHORSE_MAX_TRANSITIONS` knob rather than pinned as a class value, because pinning
  it would take the env var away.
* `resolve-operator.md`'s final response was `{"resolve_status": {"decision", "summary"}}`
  and no branch ever read `summary`. Unwrapping the envelope for `returns=` renamed it to
  `notes`, the name every other reply in this flow uses for the same thing.
* the pre-rendered reference (the internal author-workflow-python plan) leaves this flow out
  by design — it gathers the main graph only and says the two `flows:` sub-graphs "are
  their own state machines … each is its own `Workflow` subclass, reached with
  `self.handoff(...)`, and each would get this same treatment in its own module." This
  module is that treatment.
"""
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

#: Granularity replans before the plan stage is handed to the operator. The YAML wrote
#: this as the string `"2"` in `vars` and compared it with a `>=` branch condition.
MAX_PLAN_REWORKS = 2
#: Autonomous plan-stage resolutions before every later block goes to a human.
MAX_PLAN_RESOLVES = 2
#: Bounded repairs of one invalid finding record before the unit is marked `blocked` and
#: the loop moves on. A unit must never wedge the survey.
MAX_RECORD_FIXES = 2
#: Partition reworks before the clustering stage is handed to the operator.
MAX_PARTITION_REWORKS = 3
#: Autonomous partition-stage resolutions before every later block goes to a human.
MAX_PARTITION_RESOLVES = 2
#: Autonomous resolutions of a coverage failure before every later one goes to a human.
MAX_VERIFY_RESOLVES = 2
#: The three operator-resolution turns run under `timeout: infinity` in the YAML. They
#: stand in for a human, so a wall-clock ceiling on them is the wrong bound entirely —
#: the flow is already blocked at that point and the only question is what unblocks it.
UNBOUNDED = float("inf")


class Surveyor(Workflow):
    """Survey a repo against one rubric, exhaustively, one unit at a time.

    The rubric is the only project-facing input: it names the cross-cutting concern
    (what counts as a finding, what "clean" means) and points at the repo skills that
    carry the stack mechanics. Everything else is a path convention under `survey_dir`.
    """

    #: The concern being surveyed. `load_survey_config` fails the flow when it names no
    #: readable file — a survey with no rubric has nothing to be exhaustive *about*.
    rubric: str = "docs/survey/rubric.md"
    #: Where this survey's own artifacts live: rules, frozen inventory, finding records,
    #: partition, unit manifest and the operator context file.
    survey_dir: str = "docs/survey"
    #: What emission appends its generated bullets to, inside its own fence. Blank — the
    #: normal case — means the backlog ostler keeps for this repo.
    backlog: str = ""
    #: `auto` lets the resolver agent stand in for the human at every gate; `human` sends
    #: every block straight to the context file. Anything else reads as `auto`, which is
    #: the YAML's `cases: {human: …}` with `default:` on the autonomous arm.
    operator_mode: str = "auto"

    def setup(self) -> SurveyConfig:
        """Resolve the survey's paths and prove the rubric exists.

        `load_config`. A state would be the wrong home: every state below reads these
        paths and none of them decides one.
        """
        return self.call(
            load_survey_config, self.rubric, self.survey_dir, self.backlog
        )

    def labels(self) -> dict[str, str]:
        """Which unit the survey is on, and how far along — the YAML's `labels:` block.

        Both dimensions come off `select_unit`, exactly as the YAML read them with
        `get_node_output('select_unit', …)`. Before the first pick there is nothing to
        read, and that is the normal state of the run's first transition.
        """
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

    # --- granularity: plan the units, then freeze them ----------------------

    def start(self) -> Continue:
        """Decide whether the granularity planner needs to run at all.

        `check_inventory` + `decide_plan`. Two things beat the planner, and both are
        about not re-deciding a decision a run already made: a frozen inventory (a prior
        run or a resume already materialized the list, and the survey must consume *that*
        list), and operator-pinned rules.
        """
        check = self.call(check_inventory, self.ctx.inventory, self.ctx.rules)
        if check.needs_plan:
            return Continue(check, self.plan)
        return Continue(check, self.expand)

    def plan(
        self, plan_rework: int = 0, plan_errors: str = "", plan_resolve: int = 0
    ) -> Continue | Await:
        """One bounded judgment: what a unit *is* for this rubric, in this repo.

        `plan_units` + `decide_plan_result`. The planner writes the enumeration rules;
        `expand` is what turns them into units, and a rules file that expands to nothing
        is what sends the flow back here with `plan_errors` set.
        """
        result = self.agent(
            "prompts/surveyor/plan-units.md",
            returns=PlanResult,
            # high: this is the one call in the flow that decides the *shape* of the
            # whole survey — get the granularity wrong and every unit below is wrong.
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
        """Materialize the frozen unit list from the rules — or consume the frozen one.

        `expand_inventory` + `decide_expand` + `guard_plan` + `incr_plan`. An inventory
        already on disk is the coverage baseline and is never re-expanded: a resume that
        produced a *different* list would silently rewrite the claim the survey ends up
        making.

        An expansion that yields nothing is a granularity problem, not a repo with no
        surfaces, so it goes back to the planner with the errors — bounded, and the
        operator gate is where the bound lands.
        """
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
        """`gate_plan`: hand the granularity block to the resolver, or to the human.

        Not a state — it is the routing half of a branch, and it is called from the two
        states that can decide the plan stage is stuck. `_`-prefixed so state discovery
        does not pick it up.
        """
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
        """Investigate a granularity block, then park for the operator.

        `resolve_plan` + `incr_plan_resolve` + `await_plan`. The resolver never decides
        on the operator's behalf — it only investigates and writes findings into the
        context file, so the block always ends in an `Await`. Re-entering `plan` on
        resume *is* the re-verification: it re-reads the context file the human's answer
        just updated.
        """
        self.logger.info("resolving the granularity block", extra={"activity": True})
        self.agent(
            "prompts/surveyor/resolve-operator.md",
            returns=OperatorResolution,
            # high, and unbounded: it is investigating a block, with full tool access.
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

    # --- the per-unit loop --------------------------------------------------

    def pick(self, verify_resolve: int = 0) -> Continue:
        """Take the next pending unit, or fall through to the coverage gate.

        `select_unit` + `decide_unit`. "No unit left" is the loop's success exit rather
        than a problem: the empty pending set *is* the exhaustiveness proof.
        """
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
        """Assess one unit against the rubric and write its finding record.

        `assess_unit` + `decide_assess`. A state holding nothing but the turn: it is the
        expensive thing in the loop and the checkpoint is written *before* a state runs,
        so keeping validation and marking downstream is what makes a resume cheap.

        `split` is the granularity escape hatch — a unit too big to assess faithfully in
        one context is replaced by its children rather than sampled.
        """
        self.logger.info(
            "assessing %s %s%s",
            unit_kind,
            unit_id,
            f" · {progress}" if progress else "",
            extra={"activity": True},
        )
        result = self.agent(
            "prompts/surveyor/assess-unit.md",
            returns=UnitAssessment,
            # medium: reads one unit and the rubric's skills and judges against them.
            # The exhaustiveness is the loop's job; this turn's job is one surface.
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
        """Replace a too-big unit with its immediate children, or mark it and move on.

        `split_unit` + `decide_split` + `mark_unit_unsplit`. A split that cannot happen
        (a file unit, a folder with no children) must not wedge the survey, so the unit
        is marked with the split errors as its reason and the loop continues — the same
        give-up shape the record-fix loop ends in.
        """
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
        """Check the record the turn wrote, then take the unit off the pending list.

        `validate_record` + `decide_record` + `guard_record_fix` + `mark_unit` +
        `mark_unit_unfixable`. Validation is deterministic and hard, so the fix loop is
        bounded and its end is a `blocked` unit with the errors as its reason rather than
        a stuck survey. `mark_unit` writes a stub record when none exists, which is what
        keeps the coverage gate downstream able to account for the unit either way.
        """
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
        """One bounded repair of an invalid record, then re-validate.

        `fix_record` + `incr_record_fix`. The reply is advisory — `validate_record` is
        what decides — so nothing branches on it and the loop re-checks either way.
        """
        self.agent(
            "prompts/surveyor/fix-record.md",
            returns=RecordFix,
            # medium: a mechanical repair against a named list of validation errors.
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

    # --- the coverage gate --------------------------------------------------

    def verify(self, verify_resolve: int = 0) -> Continue | Await:
        """Every frozen unit accounted for, with a record, and no silent shrinkage.

        `verify_records` + `decide_verify` + `gate_verify` + `guard_verify_resolve`. The
        loop's empty select is the proof; this is what makes it auditable. A survey that
        surveyed *nothing* passes here — `holds` is true and `nothing_surveyed` says why
        — which is the YAML's branch read literally: only the string `"no"` gates.
        """
        result = self.call(verify_records, self.ctx.inventory, self.ctx.findings_dir)
        if result.holds:
            return Continue(result, self.partition)
        notes = result.verify_errors or result.verify_report
        if self.operator_mode == "human" or verify_resolve >= MAX_VERIFY_RESOLVES:
            # No counter reset, unlike the other two awaits: once the autonomous budget
            # is spent, every later coverage failure goes to the human.
            return Await(self._context, notes, self.pick, verify_resolve=verify_resolve)
        return Continue(
            result, self.resolve_verify, notes=notes, verify_resolve=verify_resolve
        )

    def resolve_verify(self, notes: str, verify_resolve: int = 0) -> Await:
        """Investigate a coverage failure, then park for the operator.

        `resolve_verify` + `incr_verify_resolve` + `await_verify`. The resolver never
        decides on the operator's behalf — it only investigates and writes findings into
        the context file, so the block always ends in an `Await`. Re-entering `pick` on
        resume *is* the re-verification: the unit loop and `verify` both re-read
        whatever the human's answer changed (usually a `blocked` unit back to `pending`).
        """
        self.logger.info("resolving the coverage block", extra={"activity": True})
        self.agent(
            "prompts/surveyor/resolve-operator.md",
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

    # --- clustering, and the artifacts author reads -------------------------

    def partition(
        self,
        partition_rework: int = 0,
        partition_errors: str = "",
        partition_resolve: int = 0,
    ) -> Continue | Await:
        """Cluster the findings into work items, losslessly.

        `partition_findings` + `decide_partition_agent` + `validate_partition` +
        `decide_partition` + `guard_partition` + `incr_partition`. The gate that matters
        is the orphan sweep: every non-clean unit must map into at least one cluster, so
        a partition cannot quietly drop a finding on its way to becoming a backlog item.
        """
        result = self.agent(
            "prompts/surveyor/partition-findings.md",
            returns=PartitionProposal,
            # high: reads every finding record at once and decides what work items the
            # whole survey becomes — the second of the flow's two shaping judgments.
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
        """`gate_partition`: hand the clustering block to the resolver, or to the human.

        The `_gate_plan` shape again, at the flow's other end. Not a state.
        """
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
        """Investigate a clustering block, then park for the operator.

        `resolve_partition` + `incr_partition_resolve` + `await_partition`. The resolver
        never decides on the operator's behalf — it only investigates and writes
        findings into the context file, so the block always ends in an `Await`.
        Re-entering `partition` on resume *is* the re-verification: it re-reads the
        context file the human's answer just updated.
        """
        self.logger.info("resolving the partition block", extra={"activity": True})
        self.agent(
            "prompts/surveyor/resolve-operator.md",
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
        """Write the generated backlog bullets and the unit-level manifest.

        `emit_artifacts` + `decide_emit` + `survey_done` / `survey_failed`. Unlike the
        parity flow, emission failing is fatal here — the YAML routes its `default:` arm
        to a `fail` node — because a partial backlog/traceability pair cannot prove the
        generated work covers the completed survey.

        The result is what `handoff` hands back to `author`.
        """
        result = self.call(
            emit_artifacts,
            self.ctx.partition,
            self.ctx.inventory,
            self.ctx.backlog,
            self.ctx.unit_manifest,
        )
        if not result.emit_ok:
            raise WorkflowFailed(
                f"survey emission failed: {result.emit_errors or result.emit_note}"
            )
        return Done(result)


__all__ = ["Surveyor"]
