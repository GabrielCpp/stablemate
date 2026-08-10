"""Plan QA for a story, run it, and refuse to believe it passed — the port of
`coder/workflow.yaml`'s `flows.qa` (91 nodes, lines 2440-3593).

Reached from the main graph as the `qa_phase` flow node, and standalone as
`workhorse-coder run qa`. It is the densest graph in the four workflows, and it is one
control plane rather than a pipeline::

    context ⇄ repair → plan ⇄ review → stack ⇄ setup-fix → run → assess
      → evidence → audit → backlog → (triage | feedback → regression ⇄ fix) → sentinels

Ninety-one nodes become twenty-five states. Twenty-nine of the ninety-one are `type: branch`
routers reading a value produced directly above them, so each folds into the `if` at the end
of the state that produced it; eleven are `seed`/`incr` counter nodes and `emit-kv.py` flag
setters, which are fields of the loop carrier now; four more are `emit-kv.py` terminals,
which are `Done(...)`.

**Everything the graph loops on travels as one `QaLoop`.** Eighteen flow vars is past the
point where threading each as its own state parameter is legible — see the model. This is
the first port to need the shape, and it needed no driver change: a pydantic model is a
legal state parameter, so a checkpoint carries the whole loop and a resume rebuilds it.

Divergences from the YAML, all deliberate:

* **`add_dirs` is `affected_repo_paths`, not the workspace dirs.** Every agent turn in this
  flow reads `{{ affected_repo_paths }}` — the repos the *plan* touches, decoded by
  `resolve_impl_context` — where `dev` and `docs` pass the whole workspace. `qa` never calls
  `resolve_workspace_dirs` at all, and the port keeps the narrower grant.
* `repair_qa_context` declared two output keys on one agent node. It returns a two-field
  model here (`QaContextRepair`), because the driver builds one output key per top-level
  field — see `shared/schemas/qa.py`. No other agent turn in the four workflows has this shape.
* **an empty `story_path` ends the flow `exhausted`, it does not fail it.** `docs` raises on
  the same condition; `qa`'s `decide_qa_story` routed to `mark_qa_exhausted`, and the parent
  graph's `decide_qa_outcome` has an arm for it. Preserved as the YAML had it.
* the budgets are `ClassVar` ints. None is declared in `flows.qa.vars` — the guards carry
  branch literals and the comments cite `vars.max_*`
  names that do not exist. Same inert-var finding as `dev`'s `max_validate_reworks`;
  recorded in the progress ledger.
* **the QA-plan budget is one total across three attributed counters.** Schema validation,
  pre-run review, and post-run findings retain separate counters for diagnosis, but all draw
  from one four-repair ceiling. The total is derived from those checkpointed counters, so an
  old resume neither resets its allowance nor needs a state migration.
* `clear_qa_gate_state` is `QaLoop.cleared()`, called on the way out of the plan turn rather
  than as a node. It blanked five keys and left the two context ones alone; the model does
  the same, and says so.
* `decide_qa_run`'s `blocked: file_backlog_items` arm is unreachable and stays that way:
  `decide_qa_assessment_runner_status` sends `blocked` to the setup loop three branches
  earlier, so the runner status cannot still be `blocked` by the time `decide_qa_run` reads
  it. Recorded rather than tidied.
* `await_operator_qa` re-emitted `plan_rework_count` — a key `flows.qa` neither declares nor
  reads (it is `qa_plan_rework_count` here), left over from `flows.dev`'s copy of the node.
  Nothing observes it, and a flow's vars are isolated, so it is dropped. Recorded as a
  finding, not a narrowing: there is no reader to narrow.
* **`apply_resolved` reads the QA budget it spends.** In the YAML nothing did, and the
  operator gate's return leg is reachable from the context loop, whose own counter advances
  only on a repaired packet — so an unmappable packet laps context → repair → gate → resolve
  → read → apply → context forever, three agent turns a lap, until the driver's transition
  budget ends the run. The counter was already being incremented; the guard is new.
* the three `mark-*` scripts (`mark-qa-assessment-failed.py`, `mark-qa-audit-failed.py`,
  `mark-regression-unresolved.py`) each printed one `qa_result`. They are the assignment at
  the deciding site, with the same default strings.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.backlog import file_backlog_items
from workhorse_workflows.coder.shared.dev import read_operator_context, resolve_impl_context
from workhorse_workflows.coder.shared.docs import detect_okf_docs
from workhorse_workflows.coder.qa.nodes.evidence import verify_qa_evidence
from workhorse_workflows.coder.qa.nodes.hygiene import check_sentinel_ids, flush_root_screenshots
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.qa.nodes.qa import (
    clear_qa_evidence,
    ensure_stack,
    record_qa_giveup,
    run_qa_plan,
    validate_qa_plan,
)
from workhorse_workflows.coder.qa.nodes.regression import (
    detect_regression_platform,
    run_regression_suite,
)
from workhorse_workflows.coder.shared.review import check_feedback
from workhorse_workflows.coder.shared.story import prepare_story, stamp_specs
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.qa import (
    QaAssessment,
    QaAudit,
    QaContextRepair,
    QaFlowResult,
    QaLoop,
    QaPlanResult,
    QaPlanReview,
    QaReport,
    QaResult,
    QaTriage,
    RegressionFix,
    SetupResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels

UNBOUNDED = float("inf")


def _finding(passed: bool, notes: str) -> str:
    """A gate's notes when it failed, and nothing when it passed.

    The `*_notes` fields on `QaLoop` are *diagnostics*: `plan_qa` renders them under an
    instruction to repair the existing plan from what the gates said about it. A gate that
    passed said nothing to repair, so storing its verdict there hands the next plan turn a
    contradiction — "repair this from its diagnostics" over the diagnostic "QA plan is
    valid."

    That is not a cosmetic mismatch. A gate's notes are written on the branch it takes and
    then survive `cleared()`, so a *passing* verdict reaches `plan` whenever the flow
    re-enters it from somewhere other than the gate that failed — re-planning after an
    OKF-context rebuild is the standing case. A coder run did exactly this, and the agent
    read the brief correctly: it answered "I'm leaving both files unchanged", the plan then
    failed validation on the defect nobody had told it about, and the no-op turn cost one
    of the shared plan-repair budget.

    Each gate spells its own success differently (`status == "passed"`, `disposition ==
    "approved"`, a verdict plus a refutation class), so the predicate stays at the call
    site and only the rule — a pass is not a finding — lives here.
    """
    return "" if passed else notes


def _scoped_to_the_plan(review: QaPlanReview) -> tuple[QaPlanReview, int]:
    """Hold a plan review to the authority its own brief already claims, and count the misses.

    `review-qa-plan.md` states it twice — the heavyweight shared stack belongs to
    `ensure_stack`, and a finding the author cannot act on inside a plan file spends the
    repair budget and returns the same worklist next pass. Reviews observed in real runs
    refuse plans over exactly that anyway: an emulator that is not running, a stack the plan
    was forbidden to start. Prose in a brief is not a filter, and free-form `notes` left the
    flow nothing to filter *with*; a closed `scope` on each finding does.

    Two things happen here, and the second is the one that pays. Out-of-scope findings are
    dropped from the repair contract — the author is not sent to fix what it may not touch.
    And when *every* finding was out of scope, the refusal itself is overturned: a `revise`
    with nothing left in it is the case the brief says to approve, and letting it stand costs
    a `power="high"` replan turn plus a second full review to arrive back here unchanged.

    A `revise` carrying no findings at all is left alone. It may be a legacy shape or a prose
    refusal, and nothing here can tell it from a real one — the safe arm is the flow's own.

    Returns the review to act on, and how many findings were dropped.
    """
    outside = [finding for finding in review.findings if finding.scope != "plan"]
    if not outside:
        return review, 0
    kept = [finding for finding in review.findings if finding.scope == "plan"]
    ceded = "; ".join(f"{finding.scope}: {finding.issue}".strip() for finding in outside)
    update: dict[str, object] = {
        "findings": kept,
        "notes": f"{review.notes}\n\nOutside the plan's authority, not sent for repair: {ceded}",
    }
    if not kept and review.disposition != "approved":
        update["disposition"] = "approved"
    return review.model_copy(update=update), len(outside)


class Qa(Workflow):
    """Run a story's QA plan, gate the evidence, audit the pass, and bound every retry."""

    #: The story slug. ostler resolves the story path, spec dir and QA dir from it.
    story: str = ""
    #: The docs repo root, when the planning documents live in a checkout of their own.
    #: Empty walks up from `repo_dir`, i.e. the docs sit beside the code.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""
    #: The epic slug. Empty finds the story under whichever epic carries it.
    epic: str = ""
    #: `auto` stands a high-effort agent in for the operator; `human` halts and waits.
    operator_mode: str = "auto"
    #: `local` — we own the code and fix it here; `dev` — we do not, so findings are
    #: reported to the tracker and the flow ends.
    target_env: str = "local"
    #: Repo-relative stack manifest `ensure_stack` reads. Passed rather than assumed: a
    #: fixer that authors it at the root while the run reads `<service>/qa-stack.yml` loops.
    qa_stack_manifest: str = "qa-stack.yml"
    #: The parent's rescope budget, seeded in and handed back bumped. The one piece of loop
    #: state this isolated flow does not own.
    triage_scope_count: int = 0
    #: `snapshot_worktree_state`'s reading from before this story's first dev turn — the
    #: paths that were already dirty then, with their bytes. The obligation packet drops the
    #: ones that still match, so QA does not write scenarios for an earlier story's
    #: abandoned work. Empty drops nothing, which is the pre-snapshot behaviour.
    preexisting: tuple[str, ...] = ()


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: The bounded retry budgets. All `ClassVar`, because none of them is a var the YAML
    #: declared — each guard carries a branch literal. See the module docstring.
    MAX_QA_REWORKS: ClassVar[int] = 3
    MAX_CONTEXT_REWORKS: ClassVar[int] = 3
    #: The two QA-plan budgets are deliberately separate. `MAX_PLAN_REWORKS` bounds the
    #: gates that judge the plan (`review-qa-plan` and the post-run assessment);
    #: `MAX_PLAN_VALIDATION_REWORKS` bounds repairs of a `qa-plan.yml` that does not parse.
    #: See `QaLoop.plan_judgement_rework` for the story that split them.
    MAX_PLAN_REWORKS: ClassVar[int] = 4
    MAX_PLAN_VALIDATION_REWORKS: ClassVar[int] = 3
    MAX_SETUP_REWORKS: ClassVar[int] = 2
    MAX_REGRESSION_FIXES: ClassVar[int] = 3
    MAX_TRIAGE_SCOPES: ClassVar[int] = 2

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its `qa/` directory."""
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    #: `ensure_stack` brings a durable app stack up and health-gates it — on a real run
    #: that is minutes of `booting app: … waiting up to 2400s`, and it is the model
    #: sitting idle, not working. Marking it keeps a slow stack out of any aggregate
    #: that would otherwise read the wait as effort.
    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack})

    #: The budgets worth grouping a query by. All eight of `QaLoop`'s counters, because
    #: this flow's whole shape is which of them ran out first.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = (
        "context_rework",
        "plan_rework",
        "plan_validation_rework",
        "plan_review_rework",
        "plan_rework_total",
        "plan_judgement_rework",
        "qa_rework",
        "setup_rework",
        "regression_fix",
        "triage_scope",
    )

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on, and what
        each gate last decided.

        `QaLoop` is threaded through every transition as a state parameter, so both are
        already in hand here and no state has to stash a copy of them. `start` and `setup`
        run before any loop exists, and simply report nothing.

        The verdicts label the spans *after* the turn that produced them, which is the
        useful direction: what a query wants is the cost of the work a `revise` caused,
        not the cost of saying the word.
        """
        loop = params.get("loop")
        if not isinstance(loop, QaLoop):
            return self.labels()
        carried = loop.model_dump() | {
            "plan_rework_total": loop.plan_rework_total,
            "plan_judgement_rework": loop.plan_judgement_rework,
        }
        return (
            self.labels()
            | counter_labels(carried, "qa", self.BUDGET_LABELS)
            | verdict_labels(carried, "qa", QaLoop.VERDICT_LABELS)
        )

    # ── context ───────────────────────────────────────────────────────────────────────

    def start(self) -> Continue | Done:
        """Clear the last run's evidence and decode what this story actually touched.

        `decide_qa_story` + `clear_qa_evidence` + `resolve_qa_context` + `detect_qa_okf`.
        All deterministic, and the one branch guards `setup`'s own output.

        `resolve_qa_context` is `resolve-impl-context.py` again — the same node `dev` and
        `docs` run — read here for the repo paths every agent turn is granted and the source
        roots the obligation packet is built from. Re-deriving it rather than reading the dev
        phase's copy is what makes a standalone re-QA of an already-built story work.
        """
        if not self.ctx.story_path:
            self.logger.info("no story to QA — nothing to run")
            return Done(QaFlowResult(triage_scope=self.triage_scope_count))
        self.call(clear_qa_evidence, self.ctx.spec_dir)
        self.call(resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path)
        okf = self.call(detect_okf_docs, self.docs_path)
        return Continue(
            okf,
            self.build_context,
            loop=QaLoop(
                triage_scope=self.triage_scope_count,
                docs_recheck_required=False,
            ),
        )

    def build_context(self, loop: QaLoop) -> Continue | Await | Done:
        """Diff the implementation against the OKF graph and demand a mappable packet.

        `build_qa_okf_context` + `validate_qa_okf_context` + `decide_qa_okf_context` +
        `guard_qa_context`. The adapter always exits zero; blocking unmapped health comes
        back as `status=invalid`, which is what the guard reads.

        This is the loop's join point — six states route back here, because a product fix, an
        operator answer or a regression fix can all change what the diff obligates.
        """
        impl = self.output(resolve_impl_context)
        build = self.call(
            build_okf_context,
            self.ctx.spec_dir,
            self.ctx.story_path,
            self._features_root,
            tuple(impl.qa_source_roots),
            "HEAD",
            "WORKTREE",
            self.docs_path,
            preexisting=tuple(self.preexisting),
        )
        result = self.call(
            validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path
        )
        loop = loop.update(
            context_status=result.status,
            context_notes=_finding(result.status == "passed", result.notes),
        )
        if result.status == "passed":
            return Continue(result, self.plan, loop=loop)
        if loop.context_rework >= self.MAX_CONTEXT_REWORKS:
            return self._exhausted(loop, f"{loop.context_rework} OKF-context repair")
        return Continue(result, self.repair_context, loop=loop)

    def repair_context(self, loop: QaLoop) -> Continue | Await | Done:
        """Ask an agent to make the packet mappable, once per rework the budget allows.

        `repair_qa_context` + `decide_qa_context_repair`. The only two-key agent turn in the
        coder: it reports whether it repaired anything *and* writes the running QA verdict,
        so a blocked repair carries its reason into the operator gate it routes to.
        """
        self.logger.info("repairing the QA obligation packet", extra={"activity": True})
        reply = self.agent(
            "prompts/repair-qa-context.md",
            returns=QaContextRepair,
            # medium: mechanical reconciliation of a diff against a graph, against a
            # validator that will re-check the result.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "context_notes": loop.context_notes,
            },
        )
        loop = loop.require_docs_recheck().with_qa(reply.qa_result)
        if reply.qa_context_repair.status == "repaired":
            return Continue(
                reply, self.build_context, loop=loop.update(context_rework=loop.context_rework + 1)
            )
        return self._gate(reply, loop)

    # ── plan ──────────────────────────────────────────────────────────────────────────

    def plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Author the QA plan, forget every previous gate's findings, and parse the result.

        `plan_qa` + `clear_qa_gate_state` + `stamp_specs_qa_plan` + `validate_qa_plan` +
        `decide_qa_plan_validation`.

        The plan turn is handed every diagnostic the loop collected — the packet's status,
        the last validation, the last review, the last run assessment, the last audit, the
        last evidence verdict — and then those are cleared, because they describe a plan that
        no longer exists. `validate_qa_plan` immediately writes a fresh one.

        The one thing not cleared is `plan_review_ledger`, handed over beside the latest
        review as `prior_plan_reviews`. A refusal describes a plan that is gone; the *demand*
        in it outlives the draft it was written against, and forgetting that is what let a
        story spend every judgement repair being told the same thing. See the field.
        """
        self.logger.info("planning QA for %s", self.ctx.story_slug, extra={"activity": True})
        self.agent(
            "prompts/plan-qa.md",
            returns=QaPlanResult,
            # medium: writing a runnable plan against a schema, from a story and an
            # obligation packet that both already exist.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
                "context_status": loop.context_status,
                "context_notes": loop.context_notes,
                "plan_validation_notes": loop.plan_validation_notes,
                "plan_review_notes": loop.plan_review_notes,
                "prior_plan_reviews": loop.prior_plan_review_brief,
                "run_assessment_notes": loop.assessment_notes,
                "audit_notes": loop.audit_notes,
                "evidence_notes": loop.qa.notes,
            },
        )
        loop = loop.cleared()
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        validation = self.call(validate_qa_plan, self.ctx.spec_dir, self.docs_path)
        loop = loop.update(
            plan_validation_notes=_finding(validation.status == "passed", validation.notes)
        )
        if validation.status == "passed":
            return Continue(validation, self.review_plan, loop=loop)
        return self._guard_plan_validation(validation, loop)

    def review_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """An independent read of a plan that already parses — does it test the story?

        `review_qa_plan` + `decide_qa_plan_review`. `revise`, and a blank taking the YAML's
        `default:`, spends a plan *review* rework; only `approved` reaches the stack.

        A refusal is also appended to `plan_review_ledger`, which the next plan turn reads
        and `cleared()` does not blank. The reviewer's own brief is deliberately unchanged:
        it judges the plan in front of it, and handing it its own past findings would anchor
        the one gate whose independence the flow is built around.

        What the reviewer returns is then held to the authority contract its own brief states,
        by `_scoped_to_the_plan` rather than by trusting it — see that function.
        """
        review = self.agent(
            "prompts/review-qa-plan.md",
            returns=QaPlanReview,
            # high: judging whether a plan actually verifies the story's claims is the
            # harder half of writing one.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "target_env": self.target_env,
            },
        )
        review, dropped = _scoped_to_the_plan(review)
        if dropped:
            self.logger.info(
                "dropped %d QA-plan review finding(s) outside the plan's authority", dropped,
                extra={"activity": True},
            )
        loop = loop.update(
            plan_review_notes=_finding(review.disposition == "approved", review.notes),
            plan_review_disposition=review.disposition,
        )
        if review.disposition == "approved":
            return Continue(review, self.stack, loop=loop)
        if review.notes.strip():
            loop = loop.update(
                plan_review_ledger=(*loop.plan_review_ledger, review.notes.strip())
            )
        return self._guard_plan_review(review, loop)

    # ── stack and run ─────────────────────────────────────────────────────────────────

    def stack(self, loop: QaLoop) -> Continue | Await | Done:
        """Bring the durable QA stack up, or send its manifest to the repair loop.

        `ensure_stack` + `decide_stack_ready`. `skip` — no manifest authored — is not a
        failure and routes exactly where `yes` does, because a story with no stack to stand
        up runs its QA the same way it always did.
        """
        status = self.call(ensure_stack, self.qa_stack_manifest, self.docs_path)
        if status.ready == "no":
            self.logger.info("QA stack did not come up: %s", status.failed_step)
            # The failure becomes the running verdict, because `block_notes` — what the
            # fixer and the operator gate are both briefed with — is composed from it. A
            # stack that never came up leaves `qa` blank otherwise, and the fixer is sent
            # to repair a stack without being told what about it broke.
            return self._guard_setup(
                status, loop.with_qa(QaResult(status="blocked", notes=status.notes))
            )
        return Continue(status, self.run, loop=loop)

    def run(self, loop: QaLoop) -> Continue:
        """Execute the plan through ostler's runner — the expensive step, and its own state.

        `run_qa_plan`. Alone, so a kill during the assessment re-enters at the assessment
        rather than re-running a QA suite that may have taken half an hour.
        """
        self.logger.info("running the QA plan", extra={"activity": True})
        result = self.call(run_qa_plan, self.ctx.spec_dir, self.docs_path)
        return Continue(result, self.assess, loop=loop.with_qa(result))

    def assess(self, loop: QaLoop) -> Continue | Await | Done:
        """Read the runner's verdict for what it means — four chained decisions, one state.

        `assess_qa_run` + `stamp_specs_qa` + `decide_qa_assessment` +
        `decide_qa_assessment_runner_status` + `decide_qa_assessment_class` +
        `decide_qa_assessment_objective` + `mark_qa_assessment_failed` + `decide_qa_run`.

        The five branches are a single sieve over one agent reply and one runner status, and
        the YAML wrote them as separate nodes only because a branch node reads one path. Each
        arm is spelled out below in the order the YAML chained them, and every fall-through
        lands on the same two loops: the plan rework, or the setup repair.
        """
        assessment = self.agent(
            "prompts/qa-story.md",
            returns=QaAssessment,
            # medium: judging a runner's output against a plan that already passed two
            # gates. The adversarial read is `audit_qa`'s job, at high.
            power="medium",
            add_dirs=self._dirs(),
            args={
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
        loop = loop.update(
            assessment_notes=_finding(assessment.disposition == "confirmed", assessment.notes),
            assessment_disposition=assessment.disposition,
            assessment_failure_class=assessment.failure_class,
        )

        if assessment.disposition == "repair_setup":
            return self._guard_setup(assessment, loop)
        if assessment.disposition != "confirmed":
            # repair_plan, extend_plan, and a blank taking the YAML's `default:`.
            return self._guard_plan(assessment, loop)

        if loop.qa.status == "blocked":
            return self._guard_setup(assessment, loop)
        if loop.qa.status not in {"passed", "failed"}:
            return self._guard_plan(assessment, loop)

        if assessment.failure_class == "product":
            # `mark-qa-assessment-failed.py`: the story is wrong, not the plan.
            failed = QaResult(
                status="failed",
                notes=assessment.notes or "QA assessment found a product defect.",
            )
            return Continue(assessment, self.backlog, loop=loop.with_qa(failed))
        if assessment.failure_class == "environment":
            return self._guard_setup(assessment, loop)
        if assessment.failure_class != "none":
            return self._guard_plan(assessment, loop)

        if assessment.objective_reached != "yes":
            return self._guard_plan(assessment, loop)

        # `decide_qa_run`. `blocked` and `invalid` were both sieved out above; the YAML's
        # arms for them are unreachable here and preserved as written.
        if loop.qa.status == "passed":
            return Continue(assessment, self.verify_evidence, loop=loop)
        return Continue(assessment, self.backlog, loop=loop)

    # ── the two verdict gates ─────────────────────────────────────────────────────────

    def verify_evidence(self, loop: QaLoop) -> Continue | Await | Done:
        """Fail closed: is the claimed pass backed by artifacts that exist on disk?

        `verify_qa_evidence` + `decide_qa_evidence`. Deterministic, and the reason a claimed
        pass is worth auditing at all — the auditor reads evidence this gate confirmed is
        there.
        """
        result = self.call(
            verify_qa_evidence, self.ctx.spec_dir, loop.qa.status, loop.qa.notes
        )
        loop = loop.with_qa(result)
        if result.status == "passed":
            return Continue(result, self.audit, loop=loop)
        if result.status in {"failed", "blocked"}:
            return Continue(result, self.backlog, loop=loop)
        return self._guard_plan(result, loop)

    def audit(self, loop: QaLoop) -> Continue | Await | Done:
        """Try to refute the pass — `decide_qa_audit` and its two follow-on branches.

        A verdict that `stands` still has to name `none` as its refutation class; anything
        else means the auditor found something it could not reconcile, and the plan rework
        loop is the arm for that. A `refuted` product contradiction is the story failing,
        which is a backlog item and a fix, not a replan.
        """
        result = self.agent(
            "prompts/audit-qa.md",
            returns=QaAudit,
            # high: adversarially re-judging captured evidence is only worth running on a
            # model that can actually refute a plausible-but-wrong pass.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_status": loop.qa.status,
                "qa_notes": loop.qa.notes,
            },
        )
        loop = loop.update(
            audit_notes=_finding(
                result.verdict == "stands" and result.refutation_class == "none", result.notes
            ),
            audit_verdict=result.verdict,
            audit_refutation_class=result.refutation_class,
        )
        if result.verdict == "stands":
            if result.refutation_class == "none":
                return Continue(result, self.backlog, loop=loop)
            return self._guard_plan(result, loop)
        if result.verdict == "refuted" and result.refutation_class == "product-contradiction":
            # `mark-qa-audit-failed.py`.
            failed = QaResult(
                status="failed",
                notes=result.notes or "QA audit found a product contradiction.",
            )
            return Continue(result, self.backlog, loop=loop.with_qa(failed))
        return self._guard_plan(result, loop)

    # ── what happens to the verdict ───────────────────────────────────────────────────

    def backlog(self, loop: QaLoop) -> Continue | Await | Done:
        """Drain separate-scope discoveries back to the author, then route on the verdict.

        `file_backlog_items` + `decide_qa`. The filer is best-effort by design and runs on
        both a pass and a failure, because a passing story can still have turned up work that
        belongs to somebody else.
        """
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
        """Classify the findings: fix them in-AC here, or hand the scope back to the author.

        `triage_qa` + `guard_triage` + `decide_triage` + `incr_triage` + `mark_qa_rescope`.

        `rescope` is the only exit that leaves the story unfinished on purpose: the triager
        amended the ACs on disk, so the parent re-enters `dev` with the bumped budget rather
        than re-running QA against a story that changed underneath it.
        """
        triage = self.agent(
            "prompts/triage-qa.md",
            returns=QaTriage,
            # medium: sorting findings into in-AC and adjacent, against a story whose ACs
            # are written down.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.qa.notes,
                "triage_scope_count": loop.triage_scope,
                "max_triage_scopes": str(self.MAX_TRIAGE_SCOPES),
            },
        )
        loop = loop.update(failure_class=triage.qa_failure_class)
        if loop.triage_scope >= self.MAX_TRIAGE_SCOPES:
            return self._fixable(triage, loop)
        if triage.triage_action == "rescope":
            self.logger.info("triage rescoped the story — handing back to dev")
            return Done(
                QaFlowResult(
                    status="rescope",
                    qa=loop.qa,
                    qa_rework=loop.qa_rework,
                    triage_scope=loop.triage_scope + 1,
                    docs_recheck_required=True,
                )
            )
        return self._fixable(triage, loop)

    def report_dev(self, loop: QaLoop) -> Done:
        """`target_env=dev`: we do not own the code, so write the findings out and stop.

        `report_qa_dev` + `mark_qa_exhausted`. The `exhausted` status is not a judgement on
        the report — it is how the parent's `decide_qa_fail` learns the story did not pass.
        """
        report = self.agent(
            "prompts/report-qa-dev.md",
            returns=QaReport,
            # medium: summarising findings that are already written down, into a tracker.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.qa.notes,
            },
        )
        self.logger.info("QA findings reported: %s", report.notes)
        return Done(
            QaFlowResult(
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
                # Not a budget that ran out — a dev target never fixes — but the parent's
                # give-up marker is written from this either way, and "0 attempts" on a story
                # nobody was ever going to rework is the same misreading in a different place.
                spent=f"{loop.qa_rework} code rework (dev target: reported, not fixed)",
            )
        )

    # ── the passing path: feedback, regression, sentinels ─────────────────────────────

    def feedback(self, loop: QaLoop) -> Continue:
        """Poll the story's inbox once before believing the pass.

        `check_qa_feedback` + `decide_qa_feedback`. Never halts and never asks: reading the
        inbox consumes it, so one dropped note buys exactly one re-QA.
        """
        note = self.call(check_feedback, f"{self.ctx.spec_dir}/feedback.md")
        if note.present:
            self.logger.info("operator feedback found — re-QA after applying it")
            return Continue(note, self.apply_feedback, loop=loop, content=note.content)
        return Continue(note, self.regression, loop=loop)

    def apply_feedback(self, loop: QaLoop, content: str) -> Continue:
        """Apply the operator's note and rebuild the context — product feedback moves it.

        `apply_qa_feedback`. It is `apply-qa-fixes.md` with an empty `qa_notes`, because
        there are no QA failures here: the note is the work. No rework is spent, which is the
        YAML's wiring — feedback is not a failure of the fix loop.
        """
        result = self._apply_fixes(qa_notes="", operator_feedback=content, power="medium")
        return Continue(
            result,
            self.build_context,
            loop=loop.require_docs_recheck().with_qa(result),
        )

    def regression(self, loop: QaLoop) -> Continue:
        """Which committed journey suites, if any, this plan put at risk.

        `detect_regression` + `gate_regression`. The detector fails **open** — an unreadable
        plan context reports `none` — because most stories have no UI layer to regress, and
        blocking them on a detector would be the wrong default.
        """
        platform = self.call(detect_regression_platform, self.ctx.spec_dir)
        if platform.platform in {"web", "mobile", "both"}:
            return Continue(platform, self.run_regression, loop=loop)
        return Continue(platform, self.finalize, loop=loop)

    def run_regression(self, loop: QaLoop) -> Continue | Await | Done:
        """Run the committed suites, and decide what a green run means given what preceded it.

        `run_regression` + `decide_regression_run` + `decide_regression_fix_applied` +
        `decide_regression_reqa_pending` + the three `emit-kv.py` flag setters around them.

        The two flags are the whole subtlety. A regression fix is a code change, and a code
        change invalidates the primary QA evidence that was captured before it — so a green
        regression run *after* a fix sends the story back through primary QA, once, and the
        `reqa_pending` flag is what stops that from repeating forever.
        """
        platform = self.output(detect_regression_platform)
        run = self.call(
            run_regression_suite, self.ctx.spec_dir, self.ctx.qa_dir, platform.platform
        )
        loop = loop.with_qa(run.as_qa_result())
        if run.status == "passed":
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
        if run.status == "blocked":
            return self._guard_setup(
                run,
                loop.update(regression_fix_applied=False, regression_reqa_pending=True),
            )
        if loop.regression_fix >= self.MAX_REGRESSION_FIXES:
            # `mark-regression-unresolved.py`, then the flags are cleared and the story
            # falls through to the ordinary QA-fix loop.
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
        """Reproduce and fix a real-stack journey failure, then run the suite again.

        `fix_regression` + `incr_regression_fix` + `mark_regression_fix_applied`. The fixer's
        own claim is not read: it returns notes and no status, and the re-run is the verdict.
        """
        platform = self.output(detect_regression_platform)
        run = self.output(run_regression_suite)
        self.logger.info("fixing the regression suite", extra={"activity": True})
        self.agent(
            "prompts/fix-regression.md",
            returns=RegressionFix,
            # high: reproducing and fixing real-stack journey failures.
            power="high",
            # 5400s: the journey suite alone takes 25-30 minutes, and 2400s forced three
            # consecutive timeout/retry cycles — a suite run plus diagnosis does not fit in
            # forty minutes.
            timeout=5400,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "platform": platform.platform,
                "service_paths": platform.paths,
                "regression_run_status": run.status,
                "regression_run_failing_tests": run.failing_tests,
                "regression_run_notes": run.notes,
                "regression_run_log_path": run.log_path,
                "regression_fix_count": loop.regression_fix,
            },
        )
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
        """The two pre-commit hygiene gates, and the only path to a passing story.

        `flush_root_screenshots` + `check_sentinels` + `decide_sentinels` + `mark_qa_passed` +
        `decide_qa_pass_report`. The sentinel gate only ever downgrades: it greps the lines
        this story added for fabricated placeholder IDs and unreconciled stubs, and a hit
        routes into the same bounded fix loop a QA failure does.
        """
        self.call(flush_root_screenshots, self.ctx.spec_dir)
        result = self.call(check_sentinel_ids, self.ctx.story_slug)
        loop = loop.with_qa(result)
        if result.status != "passed":
            return self._guard_qa(result, loop)
        if self.target_env == "dev":
            return Continue(result, self.report_dev_pass, loop=loop)
        self.logger.info("QA passed for %s", self.ctx.story_slug)
        return Done(
            QaFlowResult(
                status="passed",
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    def report_dev_pass(self, loop: QaLoop) -> Done:
        """`target_env=dev`: summarise what passed to the tracker, then finish green."""
        self.agent(
            "prompts/report-qa-dev-pass.md",
            returns=QaReport,
            # medium: the same summarising job as `report_qa_dev`, on a green story.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.block_notes,
            },
        )
        return Done(
            QaFlowResult(
                status="passed",
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    # ── the fix loop ──────────────────────────────────────────────────────────────────

    def apply_fixes(self, loop: QaLoop) -> Continue:
        """Fix what QA found, spend a rework, and re-derive the context before re-planning.

        `apply_qa_fixes` + `incr_qa`. This is the loop that has to actually converge within
        the budget, which is why it runs at high power.
        """
        self.logger.info("applying QA fixes", extra={"activity": True})
        result = self._apply_fixes(qa_notes=loop.qa.notes, operator_feedback=None, power="high")
        return Continue(
            result,
            self.build_context,
            loop=loop.update(
                qa=result,
                qa_rework=loop.qa_rework + 1,
                docs_recheck_required=True,
            ),
        )

    # ── the setup-repair loop ─────────────────────────────────────────────────────────

    def setup_fix(self, loop: QaLoop) -> Continue | Await | Done:
        """Repair the stack manifest that would not come up, then try it again.

        `setup_fix` + `incr_setup` + `decide_setup`. `unfixable` — the YAML's default for a
        fixer that produced nothing — escalates to the operator rather than looping.

        `stack_manifest` is passed rather than assumed: this node's whole job is repairing it,
        and a fixer that authors `qa-stack.yml` at the root while the run reads
        `<service>/qa-stack.yml` loops forever on `skip`.

        `qa_run_plan`/`qa_stack` come from the same `resolve_impl_context` the flow already
        read: the prompt lists the touched layers' QA skills from them, and each says how to
        bring its layer up — which is exactly this node's job. Omitting them left the prompt
        on its `_(none resolved)_` fallback, telling the fixer to guess from the plan's smoke
        commands while the resolved answer sat one `self.output` away.
        """
        self.logger.info("repairing the QA stack", extra={"activity": True})
        impl = self.output(resolve_impl_context)
        result = self.agent(
            "prompts/setup-fix.md",
            returns=SetupResult,
            # high: diagnosing and standing up a broken dev stack is non-trivial agentic
            # work; 2400s because compose, emulators, `npm ci` and browser installs are slow
            # but bounded.
            power="high",
            timeout=2400,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.block_notes,
                "stack_manifest": self.qa_stack_manifest,
                "qa_run_plan": impl.qa_run_plan,
                "qa_stack": impl.qa_stack,
            },
        )
        loop = loop.update(
            setup_rework=loop.setup_rework + 1,
            docs_recheck_required=True,
        )
        if result.status == "unfixable":
            return self._gate(result, loop)
        return Continue(result, self.stack, loop=loop)

    # ── the operator gate ─────────────────────────────────────────────────────────────

    def resolve_operator(self, loop: QaLoop) -> Continue | Await:
        """Stand in for the operator on a QA block, or escalate to a human.

        `resolve_qa` + the `await_operator_qa` that followed it unconditionally. Split for the
        reason `dev` records: the driver's `Await` waits unconditionally, so whether to wait
        has to be decided before it is reached. A blank decision matches neither arm and takes
        the conservative one — wait for a person.
        """
        self.logger.info("resolving the QA block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # high, and unbounded: standing in for a human, with full tool access, on the
            # highest-stakes decision in the flow.
            power="high",
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "block_kind": "qa",
                "block_notes": loop.block_notes,
            },
        )
        if result.decision == "answered":
            return Continue(result, self.read_operator, loop=loop)
        # No ask — see `dev.flow.resolve_plan`: the escalating resolver's note is already in
        # this file, and `Await` writes its `questions` over the top of whatever is there.
        return Await(self._context, "", self.read_operator, loop=loop)

    def read_operator(self, loop: QaLoop) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose.

        `await_operator_qa`'s consume half + `decide_operator_scope_qa`. An `epic`-scoped
        answer says the premise was wrong, which no amount of QA fixing reaches — the parent
        graph re-derives the epic from it.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("operator scoped the block to the epic — handing back to replan")
            return Done(
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

    def apply_resolved(self, loop: QaLoop, content: str) -> Continue | Done:
        """Apply the operator's answer as a QA fix, and spend a rework on it.

        `apply_qa_resolved` + `incr_qa`. The same prompt `apply_qa_fixes` runs, at medium
        rather than high, because the hard thinking was the operator's.

        The budget is re-read *here* rather than only in `_guard_qa`, which is the divergence
        from the YAML. `_guard_qa` bounds the fix loop that goes through it; this state is the
        far end of the operator gate, and the gate is reachable from the context loop
        (`repair_context` → `_gate`) whose own counter only advances on a *repaired* packet.
        A packet that stays unmappable therefore cycles context → repair → gate → resolve →
        read → apply → context with no counter moving at all, three agent turns a lap — one of
        them the unbounded-timeout resolver — until the driver's transition budget kills the
        run. Spending `qa_rework` per lap is what the increment below was already for; all
        that was missing is somebody reading it.
        """
        result = self._apply_fixes(
            qa_notes=loop.qa.notes, operator_feedback=content, power="medium"
        )
        loop = loop.update(
            qa=result,
            qa_rework=loop.qa_rework + 1,
            docs_recheck_required=True,
        )
        if loop.qa_rework >= self.MAX_QA_REWORKS:
            self.logger.info("operator loop is out of QA reworks — ending the flow exhausted")
            return self._exhausted(loop, f"{loop.qa_rework} operator-guided rework")
        return Continue(result, self.build_context, loop=loop)

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _guard_plan(self, result: object, loop: QaLoop) -> Continue | Done:
        """Spend the post-run component of the QA-plan judgement budget."""
        if loop.plan_judgement_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return Continue(result, self.plan, loop=loop.update(plan_rework=loop.plan_rework + 1))

    def _guard_plan_validation(self, result: object, loop: QaLoop) -> Continue | Done:
        """Spend a schema-validation repair — a budget of its own, not the judgement one.

        A `qa-plan.yml` that does not parse is a mechanical defect, and repairing it says
        nothing about whether the plan tests the story. Charging it to the same ceiling as
        the reviewer let a run of schema typos exhaust the story before any gate had read
        the plan for coverage; `QaLoop.plan_judgement_rework` records the case.
        """
        if loop.plan_validation_rework >= self.MAX_PLAN_VALIDATION_REWORKS:
            return self._exhausted(
                loop, f"{loop.plan_validation_rework} QA-plan schema repair"
            )
        return Continue(
            result,
            self.plan,
            loop=loop.update(plan_validation_rework=loop.plan_validation_rework + 1),
        )

    def _guard_plan_review(self, result: object, loop: QaLoop) -> Continue | Done:
        """Spend the review component of the QA-plan judgement budget."""
        if loop.plan_judgement_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return Continue(
            result,
            self.plan,
            loop=loop.update(plan_review_rework=loop.plan_review_rework + 1),
        )

    def _guard_setup(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_setup`: another repair attempt, or the operator gate."""
        if loop.setup_rework >= self.MAX_SETUP_REWORKS:
            return self._gate(result, loop)
        return Continue(result, self.setup_fix, loop=loop)

    def _guard_qa(self, result: object, loop: QaLoop) -> Continue | Done:
        """`guard_qa` + `guard_qa_bonus` + `decide_bonus_class` + `grant_qa_bonus`.

        Past the budget there is exactly one more pass available, and only for an `evidence`
        failure class: the finding is that the proof is missing rather than the code, so one
        verification-only attempt is cheap and often decisive. `code`, `environment` and an
        untriaged blank earn nothing.
        """
        if loop.qa_rework < self.MAX_QA_REWORKS:
            return Continue(result, self.apply_fixes, loop=loop)
        if loop.bonus_used or loop.failure_class != "evidence":
            return self._exhausted(loop, f"{loop.qa_rework} code rework")
        self.logger.info("granting the one verification-only bonus pass")
        return Continue(result, self.apply_fixes, loop=loop.update(bonus_used=True))

    def _fixable(self, result: object, loop: QaLoop) -> Continue | Done:
        """`decide_qa_fixable`: in a `dev` run the findings are reported, not fixed."""
        if self.target_env == "dev":
            return Continue(result, self.report_dev, loop=loop)
        return self._guard_qa(result, loop)

    def _gate(self, result: object, loop: QaLoop) -> Continue | Await:
        """`gate_qa`: hand the block to the auto-operator, or halt for a human."""
        if self.operator_mode in {"human", "operator"}:
            return Await(self._context, loop.block_notes, self.read_operator, loop=loop)
        return Continue(result, self.resolve_operator, loop=loop)

    def _exhausted(self, loop: QaLoop, spent: str = "") -> Done:
        """`mark_qa_exhausted`: the budget is spent, and the parent decides what that costs.

        `spent` names *which* of the four budgets ran out, because the parent stamps it onto
        the story and into the marker commit. Without it the give-up always reported the
        code-rework count, so a story that spent every QA-plan repair and never got as far as
        a code fix was filed as "0 attempts" — which reads as an untried story rather than an
        exhausted one, and is the version a human triaging the marker would act on.

        `record_qa_giveup` is the other half of that same fix. Naming the budget tells the
        human *how* the flow stopped; the gate diagnostics on `loop` are the only record of
        *why*, and they die here otherwise — `QaFlowResult` carries the code-rework verdict
        and the plan gates never write to it. The node persists them beside the story, which
        is where `flag_qa_failure` already looks for the file it points the status at.
        """
        self.call(
            record_qa_giveup,
            self.ctx.spec_dir,
            self.ctx.story_slug,
            spent,
            plan_review_notes=loop.plan_review_notes,
            plan_review_ledger=tuple(loop.plan_review_ledger),
            plan_validation_notes=loop.plan_validation_notes,
            assessment_notes=loop.assessment_notes,
            audit_notes=loop.audit_notes,
            context_notes=loop.context_notes,
            evidence_notes=loop.qa.notes,
        )
        return Done(
            QaFlowResult(
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                spent=spent,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    def _apply_fixes(
        self, *, qa_notes: str, operator_feedback: str | None, power: str
    ) -> QaResult:
        """`apply-qa-fixes.md`, which three nodes ran with three different argument sets.

        `operator_feedback` is omitted rather than passed empty on the plain fix path,
        because that node's YAML args did not include the key at all.
        """
        args: dict[str, object] = {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "qa_dir": self.ctx.qa_dir,
            "qa_notes": qa_notes,
        }
        if operator_feedback is not None:
            args["operator_feedback"] = operator_feedback
        return self.agent(
            "prompts/apply-qa-fixes.md",
            returns=QaResult,
            power=power,
            add_dirs=self._dirs(),
            args=args,
        )

    @property
    def _features_root(self) -> str:
        """Where the OKF feature docs live, as `detect_qa_okf` resolved it."""
        return self.output(detect_okf_docs).features_root

    @property
    def _context(self) -> Path:
        """The file an `Await` writes its questions into: `<story-folder>/context.md`."""
        return paths.story_context_path(self.ctx.story_path)

    def _dirs(self) -> list[str]:
        """The repos this story's plan touches — every agent turn's `add_dirs`.

        `dev` and `docs` grant the whole workspace; `qa` grants only `affected_repo_paths`,
        which is what its YAML did at all eleven agent nodes.
        """
        return list(self.output(resolve_impl_context).affected_repo_paths)


__all__ = ["Qa"]
