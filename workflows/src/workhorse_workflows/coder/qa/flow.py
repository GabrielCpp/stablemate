"""Plan QA for a story, run it, and refuse to believe it passed — the port of
`coder/workflow.yaml`'s `flows.qa` (91 nodes, lines 2440-3593).

Reached from the main graph as the `qa_phase` flow node, and standalone as
`workhorse-coder run qa`. It is the densest graph in the four workflows, and it is one
control plane rather than a pipeline::

    context ⇄ repair → stack ⇄ setup-fix → plan ⇄ review → run → assess
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
* **a gate's findings are routed by scope, not all billed to the plan author.** The YAML sent
  every refusal from `decide_qa_assessment`, `decide_qa_audit` and the plan review to the
  replan loop, because all three returned prose. All three return structured findings with a
  closed `scope` now, and `_routed` sends each to the loop that can repair it: `product-test`
  to the fix loop, `plan` to the replan loop, `stack` to setup. Prose with no findings still
  takes the YAML's arm, so nothing that worked before stops working.
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

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
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
    QaFinding,
    QaFlowResult,
    QaLoop,
    QaPlanResult,
    QaPlanReview,
    QaReport,
    QaResult,
    QaRunResult,
    QaTriage,
    RegressionFix,
    SetupResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, progress_verdict, verdict_labels

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


def _blocked_problems(result: QaRunResult) -> tuple[str, ...]:
    """The runtime requirements a `blocked` run named, sorted; empty for every other status.

    Read off the runner payload rather than parsed back out of `notes`, and sorted because
    the runner builds the list by walking the plan's `targets` mapping — two runs of the same
    plan naming the same two missing requirements in a different order are the same bundle,
    and the comparison in `_guard_setup` is about sameness.
    """
    if result.status != "blocked":
        return ()
    problems = result.ostler.get("problems")
    if not isinstance(problems, list):
        return ()
    return tuple(sorted(str(problem) for problem in problems))


def _failure_signature(result: QaRunResult) -> tuple[str, ...]:
    """What a failing run failed at, as a fingerprint two runs can be compared on.

    One entry per non-passing scenario — its id, its status, and how far it got before it
    stopped — sorted, because the runner walks the plan's `scenarios` list and two runs of a
    repaired plan may order them differently while failing identically.

    The assertion counts are in the fingerprint on purpose. Scenario identity alone would
    call a repair that carried the journey three steps further "no progress" and stop a loop
    that was converging; the counts are the cheapest available proof that the run moved.
    Read off the runner payload for the reason `_blocked_problems` is — `notes` is prose.

    Empty for every status but `failed`: a `blocked` or `invalid` run never reached its
    assertions, so it has no failure to be the same as, and `_guard_setup` owns that loop.
    """
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


def _plan_finding_problems(review: QaPlanReview) -> list[str]:
    """Why a plan refusal is not an actionable repair contract. Empty means it is one.

    The same check `docs/flow.py` applies to its reviewer, and for the same reason: a
    `revise` is a bill for a `power="medium"` re-plan plus a second `power="high"` review,
    and the flow has no way to spend that usefully on a refusal that names nothing. Free
    prose was what let `review-qa-plan` refuse repeatedly without ever converging — the
    author could not tell which demand was new, so it rewrote everything and handed the
    reviewer fresh defects.

    `id` is an opaque handle, checked for presence only. Its job is to name the same defect
    across passes, not to match a shape — enforcing the prompt's `R1` convention once turned
    a pair of correct findings into a killed run over a prefix letter.
    """
    if review.disposition != "revise":
        return []
    if not review.findings:
        return ["no findings"]
    problems: list[str] = []
    for index, finding in enumerate(review.findings, start=1):
        missing = [
            field
            for field in ("id", "target", "issue", "repair")
            if not str(getattr(finding, field)).strip()
        ]
        if missing:
            problems.append(f"finding {index} missing {', '.join(missing)}")
    return problems


def _finding_line(finding: QaFinding) -> str:
    """One structured finding as the line whoever repairs it is briefed with.

    Both axes are rendered, because both decide what happened to the finding: `scope` says
    who was billed for it and `kind` says whether it refused the plan. A give-up record
    listing four findings with no way to tell which of them actually blocked is the artifact
    a human has to reconstruct the loop from.
    """
    issue = finding.issue.rstrip(".")
    return (
        f"{finding.id} [{finding.scope}/{finding.kind}] {finding.target}: {issue}. "
        f"Repair: {finding.repair}"
    )


def _brief(findings: Sequence[QaFinding], notes: str) -> str:
    """The repair brief, composed from the findings rather than taken from the prose.

    `notes` is the gate's summary and is worth carrying, but it is not the contract — it was
    being handed to the author *as* the worklist, which meant the brief varied with how
    discursive that pass's reviewer felt. Findings first, summary last.
    """
    lines = [_finding_line(finding) for finding in findings]
    if notes.strip():
        lines.append(f"Summary: {notes.strip()}")
    return "\n".join(lines)


class RoutedFindings(NamedTuple):
    """One gate's findings split by who has the authority to repair them.

    Every gate — the plan reviewer, the post-run assessment, the audit — can find a gap whose
    repair is not the plan author's to make. Until this split existed only the reviewer's
    findings were even typed, and its out-of-scope ones were *dropped*: the flow refused to
    send the author what it may not touch, and then sent the refusal nowhere. Audit and assess
    were free prose, so every refusal they raised landed on the plan author regardless.

    That is a livelock, not an inefficiency, and a live story spent 82 minutes in it. Three
    gates each found the same missing assertion in a committed test file, each billed the one
    author who cannot write one, and each got back a plan that disclosed the gap again.
    """

    plan: list[QaFinding]
    product_test: list[QaFinding]
    stack: list[QaFinding]

    #: `plan`, split again on `kind` — the two halves partition it and their union is it.
    #: `plan` itself is what everyone downstream still reads: the author repairs both halves
    #: in one lap, so the brief and the ledger want the whole worklist, not the blocking part
    #: of it. Only the gate reads the split.
    plan_blocking: list[QaFinding]
    plan_polish: list[QaFinding]


def _route_findings(findings: Sequence[QaFinding]) -> RoutedFindings:
    """Partition findings by `scope` — the closed vocabulary is what makes this decidable.

    `review-qa-plan.md` states the boundary twice in prose — the heavyweight shared stack
    belongs to `ensure_stack`, a repair the author cannot make inside a plan file spends the
    budget and returns the same worklist next pass — and gates observed in real runs cross it
    anyway. Prose in a brief is not a filter and free-form `notes` left the flow nothing to
    filter *with*; a closed `scope` on each finding does.

    `kind` splits the `plan` half the same way and for the same reason: the prompt says in
    prose to raise everything in one pass and approve what was listed, and the reviewer
    refused four times on prose nits anyway. See `QaFinding`.
    """
    plan = [finding for finding in findings if finding.scope == "plan"]
    return RoutedFindings(
        plan=plan,
        product_test=[finding for finding in findings if finding.scope == "product-test"],
        stack=[finding for finding in findings if finding.scope == "stack"],
        plan_blocking=[finding for finding in plan if finding.kind == "coverage"],
        plan_polish=[finding for finding in plan if finding.kind != "coverage"],
    )


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
    #: And the ceiling on their *product*. The two budgets above are spent independently, so
    #: nothing stopped a story alternating between them: three schema repairs and four
    #: judgement repairs is seven laps that every individual guard considers legal, and a
    #: live story reached thirteen turns of `plan-qa` that way. This bounds the sum, so the
    #: stacked budgets can no longer multiply. It is deliberately the smaller number: a plan
    #: still being repaired on the seventh lap is not converging, and the six laps before it
    #: are the evidence.
    MAX_TOTAL_PLAN_LAPS: ClassVar[int] = 6
    #: Not a spend ceiling — a review *ceiling*, and the only one of these that changes what a
    #: finding *means* rather than how many are affordable. Past this many plan-review reworks
    #: no `plan` finding could block whatever `kind` it claimed to be, so `_validated` stops
    #: entering `review_plan` and the flow goes straight to the runner. The reviewer had two
    #: independent passes to name a coverage gap, and a gap that first appears after two
    #: repairs is far likelier a fresh nit than a newly created hole — with the `audit` gate
    #: still standing downstream either way. This is the half of the fix that does not depend
    #: on the reviewer labelling honestly, which is what makes the loop terminate rather than
    #: merely usually terminate.
    MAX_BLOCKING_PLAN_REVIEWS: ClassVar[int] = 2
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
            # To the stack, not to the plan: the planner authors against a surface it can
            # reach. `plan_authored` is cleared on the way, because this is the join point —
            # a state routing back here changed what the diff obligates, and the plan that
            # answered the old obligations must not be the one that runs.
            return Continue(result, self.stack, loop=loop.update(plan_authored=False))
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

        This state is the *first draft only*. Every later lap — a schema defect, a reviewer
        refusal, a post-run finding — goes to `repair_plan`, which edits the plan instead of
        writing a new one.
        """
        self.logger.info("planning QA for %s", self.ctx.story_slug, extra={"activity": True})
        self.agent(
            "prompts/plan-qa.md",
            returns=QaPlanResult,
            # medium: writing a runnable plan against a schema, from a story and an
            # obligation packet that both already exist.
            power="medium",
            add_dirs=self._dirs(),
            args=self._plan_args(loop),
        )
        return self._validated(loop)

    def repair_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Edit the cited part of a plan that already exists, leaving the rest byte-identical.

        Every lap after the first used to re-enter `plan`, which regenerates the whole file
        from the story. That **resamples the scenarios the reviewer already accepted**, so
        each pass handed the gate a fresh set of defects to find and the loop had no reason
        to terminate — `plan-qa` averaged 5.5 turns per story and reached 13, with the same
        demand refused pass after pass. Repairing only what was cited makes the worklist
        shrink monotonically, which is the whole mechanism by which the loop converges.

        It takes the same brief as `plan` and returns the same result, so the validation tail
        and every guard are unchanged; what differs is the instruction and the power tier.
        """
        self.logger.info("repairing the QA plan for %s", self.ctx.story_slug,
                         extra={"activity": True})
        self.agent(
            "prompts/repair-qa-plan.md",
            returns=QaPlanResult,
            # low: applying a named list of edits to a file that already exists is not the
            # work that authoring the plan was, and paying the authoring tier for it is what
            # tempted the turn to rewrite rather than repair.
            power="low",
            add_dirs=self._dirs(),
            args=self._plan_args(loop),
        )
        return self._validated(loop)

    def _plan_args(self, loop: QaLoop) -> dict[str, object]:
        """Every diagnostic the loop collected, for whichever plan turn is about to run."""
        return {
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
        }

    def _validated(self, loop: QaLoop) -> Continue | Await | Done:
        """The tail both plan turns share: clear the brief, stamp, parse, route on the parse.

        A plan that parses normally goes to `review_plan`. The one exception is the polish
        lap: `review_plan` already decided this plan was approvable and sent it here only to
        have prose corrections applied, so re-reading it with a `power="high"` gate buys
        nothing and is exactly the re-entry that made the nit loop expensive. The flag is
        cleared as it is spent, so the next plan turn — a post-run finding, an audit
        refutation — is reviewed normally.

        A reviewer that has spent `MAX_BLOCKING_PLAN_REVIEWS` is skipped for the same
        arithmetic. Past the threshold every finding it can raise is demoted to polish
        whatever `kind` it claims, so the plan reaches the runner on this lap no matter what
        comes back — and the demoted worklist then forces a mandatory `repair_plan` turn to
        produce an edit nothing downstream gates on. Entering a `power="high"` gate whose
        verdict cannot change the route is the expense, not the reviewer's judgement; the
        demotion branch in the result handler still covers the lap that *reaches* the
        threshold, which is the last one whose findings are worth repairing.
        """
        loop = loop.cleared()
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        validation = self.call(validate_qa_plan, self.ctx.spec_dir, self.docs_path)
        loop = loop.update(
            plan_validation_notes=_finding(validation.status == "passed", validation.notes)
        )
        if validation.status == "passed":
            if loop.plan_polish_pending:
                self.logger.info(
                    "QA-plan polish applied — going to the runner without a second review",
                    extra={"activity": True},
                )
                return Continue(
                    validation,
                    self.run,
                    loop=loop.update(plan_polish_pending=False, plan_authored=True),
                )
            if loop.plan_review_rework >= self.MAX_BLOCKING_PLAN_REVIEWS:
                self.logger.info(
                    "QA-plan reviewer has spent its blocking budget — going to the runner "
                    "without another review",
                    extra={"activity": True},
                )
                return Continue(validation, self.run, loop=loop.update(plan_authored=True))
            return Continue(validation, self.review_plan, loop=loop)
        return self._guard_plan_validation(validation, loop)

    def review_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """An independent read of a plan that already parses — does it test the story?

        `review_qa_plan` + `decide_qa_plan_review`. `revise`, and a blank taking the YAML's
        `default:`, spends a plan *review* rework; only `approved` reaches the runner.

        A refusal is also appended to `plan_review_ledger`, which the next plan turn reads
        and `cleared()` does not blank. The reviewer's own brief is deliberately unchanged:
        it judges the plan in front of it, and handing it its own past findings would anchor
        the one gate whose independence the flow is built around.

        What the reviewer returns is then held to the authority contract its own brief states,
        by `_routed` rather than by trusting it. The findings are also what the author is
        briefed with: `_brief` composes the worklist from them, so a refusal is a list of
        repairs rather than a paragraph to reinterpret.

        This is the cheapest of the three gates and the earliest, so a `product-test` finding
        raised here is the best-case discovery of a gap the plan cannot close — it used to be
        dropped, and the run rediscovered it forty minutes later from the audit. A refusal
        left with nothing anyone can act on is overturned to `approved`: letting it stand
        costs a `power="high"` replan plus a second full review to arrive back here unchanged.

        A refusal that names only `overclaim` or `cosmetic` findings is overturned the same
        way, and for the same arithmetic. A live story spent four review passes here: the
        first found a real evidence gap, and passes two through four raised prose nits the
        reviewer itself described as reflecting no coverage gap. Each was repaired correctly
        for about a fifth of what re-entering this gate cost, and the fourth pass exhausted
        `MAX_PLAN_REWORKS` and ended the story with no QA verdict at all — the outcome the
        reviewer's own brief calls strictly worse than QA run against a merely adequate plan.
        So a non-blocking worklist is still repaired, once, and then goes to the runner rather
        than back through here. `MAX_BLOCKING_PLAN_REVIEWS` is the same rule applied to a
        reviewer that labels a nit `coverage` to keep its refusal — but it is enforced by
        `_validated` declining to enter this node at all, because a gate whose every finding
        would be demoted cannot change where the plan goes next, and this is the most
        expensive node in the plan lane.
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
                # The cost of the verdict, never the content of the last one. The reviewer's
                # amnesia about `plan_review_ledger` is what its independence rests on; how
                # many refusals the run can still afford is not a finding.
                "review_pass": loop.plan_review_rework + 1,
                "blocking_passes_left": max(
                    0, self.MAX_BLOCKING_PLAN_REVIEWS - loop.plan_review_rework
                ),
            },
        )
        problems = _plan_finding_problems(review)
        if problems:
            raise WorkflowFailed(
                "qa-plan reviewer requested revisions with invalid structured findings: "
                + "; ".join(problems)
            )
        # After the structural check, so a malformed refusal fails on its shape rather than
        # being quietly routed elsewhere and recorded as an approval.
        routed = _route_findings(review.findings)
        blocking = routed.plan_blocking
        polish = routed.plan_polish
        # A refusal the plan cannot act on — or that names nothing that would let the story
        # ship untested — is not a refusal of the plan.
        approved = review.disposition == "approved" or not blocking
        # The plan's own worklist is recorded whichever way the flow leaves: a product-test
        # route comes back through `plan`, and the author reads these notes when it does.
        notes = _brief(routed.plan, review.notes)
        outside = [finding for finding in review.findings if finding.scope != "plan"]
        if routed.plan and outside:
            # Named rather than silently absent: a finding that vanishes from the brief and
            # then reappears in the next review with no explanation is how the reviewer and
            # the author deadlock.
            ceded = "; ".join(f"{finding.scope}: {finding.issue}".strip() for finding in outside)
            notes = (
                f"{notes}\n\nOutside the plan's authority, not sent to the plan author: {ceded}"
            )
        # The baseline the *next* pass is scored against, so a reviewer handing back a fresh
        # worklist every lap reads as `churned` rather than as four expensive passes that each
        # looked productive in isolation. Approval closes the lane, findings and verdict alike.
        ids = [] if review.disposition == "approved" else [finding.id for finding in routed.plan]
        loop = loop.update(
            plan_review_notes=_finding(approved, notes),
            plan_review_disposition="approved" if approved else review.disposition,
            plan_review_progress=progress_verdict(loop.plan_review_ids or None, ids),
            plan_review_ids=ids,
        )
        if review.disposition == "approved":
            return Continue(review, self.run, loop=loop.update(plan_authored=True))
        if routed.plan:
            loop = loop.update(plan_review_ledger=(*loop.plan_review_ledger, notes.strip()))
        # `plan_authored` rides along: a refusal routed *away* from the plan is the flow
        # deciding the plan is not what needs repairing, so the setup loop's return through
        # `stack` must reach the runner rather than buy a replan the reviewer never asked for.
        # (The product-test arm rejoins at `build_context`, which clears it again.)
        elsewhere = self._routed(
            review, loop.update(plan_authored=True), review.findings, review.notes
        )
        if elsewhere is not None:
            return elsewhere
        if not blocking and polish:
            # The correction is worth keeping; re-entering a `power="high"` gate to be told so
            # is not. One `power="low"` repair lap, then the runner — no rework is charged and
            # `plan_polish_pending` makes the skip structural, so this cannot recur. Note the
            # notes are written unconditionally: `_finding` blanks a passing gate's diagnostics
            # and the repair turn is briefed from precisely this field.
            self.logger.info(
                "the QA-plan refusal is all polish — repairing once, then straight to the runner",
                extra={"activity": True},
            )
            return Continue(
                review,
                self.repair_plan,
                loop=loop.update(plan_review_notes=notes, plan_polish_pending=True),
            )
        if not routed.plan:
            # A `revise` naming nothing the plan may touch is the case the reviewer's own
            # brief says to approve; `_plan_finding_problems` already rejected an empty one.
            self.logger.info(
                "the QA-plan refusal names nothing the plan can repair — approving",
                extra={"activity": True},
            )
            return Continue(review, self.run, loop=loop.update(plan_authored=True))
        return self._guard_plan_review(review, loop)

    # ── stack and run ─────────────────────────────────────────────────────────────────

    def stack(self, loop: QaLoop) -> Continue | Await | Done:
        """Bring the durable QA stack up, or send its manifest to the repair loop.

        `ensure_stack` + `decide_stack_ready`. `skip` — no manifest authored — is not a
        failure and routes exactly where `yes` does, because a story with no stack to stand
        up runs its QA the same way it always did.

        This sits *before* the plan lane rather than after it, which is the point: with the
        surface already up, the authoring turn can execute a scenario it has just written
        (`ostler qa run --scenario … --out-dir …`) and find out whether its locators, fixtures
        and credentials actually resolve. A live run spent whole laps discovering by workflow
        round-trip what one dry run answers — a straight apostrophe where the fixture uses
        U+2019, a password constant that disagreed with the seed script. Nothing about the
        plan changes what the stack does, so nothing is lost by standing it up first.

        `plan_authored` is why the same node serves both entries. `setup_fix` rejoins here,
        and it can be reached from the *runner* as well as from a stack that would not come
        up — so a fixer that repaired a broken emulator mid-run must return to the run, not to
        a second authoring turn. `build_context` clears the flag, because a state routing back
        to the join point changed what the diff obligates and the plan answering the old
        obligations must not be the one that runs.
        """
        status = self.call(ensure_stack, self.qa_stack_manifest, self.docs_path)
        if status.ready == "no":
            self.logger.info("QA stack did not come up: %s", status.failed_step)
            # The failure becomes the running verdict, because `block_notes` — what the
            # fixer and the operator gate are both briefed with — is composed from it. A
            # stack that never came up leaves `qa` blank otherwise, and the fixer is sent
            # to repair a stack without being told what about it broke.
            # `blocked_problems` is cleared with it: a manifest that would not come up is not
            # the runner naming a missing requirement, and leaving the last run's bundle in
            # place would let the repeat detector gate on a failure it does not describe.
            return self._guard_setup(
                status,
                loop.with_qa(QaResult(status="blocked", notes=status.notes)).update(
                    blocked_problems=()
                ),
            )
        if not loop.plan_authored:
            return Continue(status, self.plan, loop=loop)
        return Continue(status, self.run, loop=loop)

    def run(self, loop: QaLoop) -> Continue:
        """Execute the plan through ostler's runner — the expensive step, and its own state.

        `run_qa_plan`. Alone, so a kill during the assessment re-enters at the assessment
        rather than re-running a QA suite that may have taken half an hour.

        A `blocked` run also carries the runner's `problems` list onto the loop, sorted. It
        is the only structured account of what the run was missing — everything downstream
        reads `block_notes`, which is prose — and `_guard_setup` compares it against the
        bundle the last setup fixer was handed. See `QaLoop.setup_problems`.

        A `failed` run carries the equivalent for the repair loops: the scenarios it failed
        and how far each got, which `_repeating` compares against what the last repair was
        handed. See `QaLoop.repaired_failures`.
        """
        self.logger.info("running the QA plan", extra={"activity": True})
        result = self.call(run_qa_plan, self.ctx.spec_dir, self.docs_path)
        return Continue(
            result,
            self.assess,
            loop=loop.with_qa(result).update(
                blocked_problems=_blocked_problems(result),
                run_failures=_failure_signature(result),
            ),
        )

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
            # repair_plan, extend_plan, and a blank taking the YAML's `default:`. The
            # disposition says the plan did not carry the story; the findings say who
            # repairs what, and `extend_plan` in particular is routinely a missing assertion
            # in a committed test file, which no replan can add.
            elsewhere = self._routed(assessment, loop, assessment.findings, assessment.notes)
            if elsewhere is not None:
                return elsewhere
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
        else means the auditor found something it could not reconcile. A `refuted` product
        contradiction is the story failing, which is a backlog item and a fix, not a replan.

        Every other refutation used to go to the plan author on the strength of the class
        alone, and an `evidence-defect` whose repair is a dynamic assertion in a committed
        test is the case that made that wrong: the author cannot write one, so the plan came
        back disclosing the same gap and the audit refuted it again. The findings say who
        repairs each gap; `_routed` sends them there. A refutation naming no findings still
        takes the prose path to the plan, so this adds no new way to kill a passing run.
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
        if result.verdict == "stands" and result.refutation_class == "none":
            return Continue(result, self.backlog, loop=loop)
        if result.verdict == "refuted" and result.refutation_class == "product-contradiction":
            # `mark-qa-audit-failed.py`.
            failed = QaResult(
                status="failed",
                notes=result.notes or "QA audit found a product contradiction.",
            )
            return Continue(result, self.backlog, loop=loop.with_qa(failed))
        elsewhere = self._routed(result, loop, result.findings, result.notes)
        if elsewhere is not None:
            return elsewhere
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

    def apply_fixes(self, loop: QaLoop) -> Continue | Await:
        """Fix what QA found, spend a rework, and re-derive the context before re-planning.

        `apply_qa_fixes` + `incr_qa`. This is the loop that has to actually converge within
        the budget, which is why it runs at high power.

        `blocked` goes to the operator instead of round the loop again. The prompt already
        asks for it — a credential the fixer cannot hold, a product decision that is in
        neither the story nor the plan, work in a repo outside this one — and this node used
        to discard the status and re-enter `build_context` anyway. Nothing downstream can
        supply what the fixer said was missing, so every remaining rework re-asks a question
        already answered, at high power, until the budget runs out and the story is filed as
        exhausted rather than as blocked on the one thing it is actually blocked on.
        """
        self.logger.info("applying QA fixes", extra={"activity": True})
        result = self._apply_fixes(qa_notes=loop.qa.notes, operator_feedback=None, power="high")
        loop = loop.update(qa=result, qa_rework=loop.qa_rework + 1, docs_recheck_required=True)
        if result.status == "blocked":
            self.logger.info("QA fixer reported blocked; escalating: %s", result.notes)
            return self._gate(result, loop)
        return Continue(result, self.build_context, loop=loop)

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
                # The interpreter the QA runner's pre-flight actually checks: `shared/ostler_qa`
                # imports the runner as a library, so a requirement like "requires the Playwright
                # Python package" is a statement about *this* process. A fixer told only to
                # install the package repairs whichever copy `pip`/`uv tool` happens to reach,
                # reports `ready`, and the next run comes back blocked on the same bundle.
                "runtime_python": sys.executable,
            },
        )
        loop = loop.update(
            setup_rework=loop.setup_rework + 1,
            docs_recheck_required=True,
            # What this turn was asked to repair, for the next `_guard_setup` to compare the
            # next blocked run against.
            setup_problems=loop.blocked_problems,
        )
        if result.status == "unfixable":
            return self._gate(result, loop)
        return Continue(result, self.stack, loop=loop)

    # ── the operator gate ─────────────────────────────────────────────────────────────

    def resolve_operator(self, loop: QaLoop) -> Continue | Await | Done:
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
        if loop.giveup_reason:
            # The gate was the last thing between this story and a give-up, and the resolver
            # declined to be it. Parking here instead would stop the *whole* run: the story
            # drain is single-threaded, so one halted story halts every remaining epic — and
            # this flow was already about to file the story as abandoned-but-visible. So take
            # that outcome now and let the queue keep draining.
            self.logger.info("the QA resolver escalated with nothing to answer — giving up")
            return self._give_up(loop, loop.giveup_reason)
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
            # `_give_up` and not `_exhausted`: this state is the far end of the operator gate,
            # so the one consult every give-up is owed has just happened — one turn ago, on
            # the answer this lap was spent applying. Escalating again is the cycle
            # `operator_consulted` exists to stop, one loop further out.
            return self._give_up(loop, f"{loop.qa_rework} operator-guided rework")
        return Continue(result, self.build_context, loop=loop)

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _routed(
        self,
        result: object,
        loop: QaLoop,
        findings: Sequence[QaFinding],
        notes: str,
    ) -> Continue | Await | Done | None:
        """Send a gate's findings to whoever can repair them. `None` — nobody but the plan.

        Precedence is `product-test`, then `plan`, then `stack`, and the first is first
        because it is the demand a replan *cannot* close. Fixing the test closes it
        permanently, and `apply_fixes` returns through `build_context` → `plan`, so a plan
        finding raised alongside it is re-judged against the repaired surface on the next
        lap rather than lost. A `stack` finding goes to the loop that owns the manifest.

        `None` means the caller's own arm is still the right one: either every finding is
        the plan author's, or the gate named none at all and only its prose is left. Neither
        is this router's to decide, because each caller spends a different budget for it.

        Routing goes through `_fixable`, never straight to `apply_fixes`: `_fixable` is what
        keeps a `dev` run *reporting* findings instead of fixing code it does not own, and
        what charges `MAX_QA_REWORKS`. A test edit is code work, so that is the correct
        budget — the judgement budget is not charged at all.

        The brief is written into `qa.notes` with a `model_copy`, not `with_qa`, because
        `with_qa` would replace `status` too — and on the audit path the run genuinely
        passed. Both loops read the brief from there: the fixer through `apply_fixes`, the
        setup fixer through `QaLoop.block_notes`.
        """
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

    def _repeating(self, loop: QaLoop, lap: str) -> bool:
        """Has the last repair left the run failing at exactly what it failed at before?

        The guards below each bound a *count* of laps. This bounds their usefulness: once a
        repair has been paid for and the suite fails identically — same scenarios, same
        assertion depth — the next lap buys the same turn and the same re-run for the same
        answer. See `QaLoop.repaired_failures` for the story it comes from.

        `lap` is what makes it one loop's question rather than both loops'. The plan loop and
        the fix loop stamp the same field, and a plan repair hands its findings to the fix
        loop without re-running the suite — so a fix loop that compared the raw fingerprint
        would call its own first visit a stall, on the strength of a code fix nobody made.
        """
        return (
            bool(loop.run_failures)
            and loop.repaired_lap == lap
            and loop.run_failures == loop.repaired_failures
        )

    def _guard_plan(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Spend the post-run component of the QA-plan judgement budget.

        Like both guards below, this returns to `repair_plan` and not to `plan`: a finding
        against one scenario is not a reason to resample the seven the gate already passed.
        """
        if self._repeating(loop, "QA-plan repair"):
            return self._stalled(result, loop, "QA-plan repair")
        if loop.plan_judgement_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return self._plan_lap(
            result,
            loop.update(
                plan_rework=loop.plan_rework + 1,
                repaired_failures=loop.run_failures,
                repaired_lap="QA-plan repair",
            ),
        )

    def _stalled(self, result: object, loop: QaLoop, lap: str) -> Continue | Await | Done:
        """A repair loop that has stopped moving — escalate rather than spend the budget.

        The operator gate and not `_exhausted`, and that difference is the point of the
        detector. Exhaustion says "this story was tried the agreed number of times"; a stall
        says "this is not repairable from where we are repairing it", which is a decision a
        human or the auto-operator can act on — most often by classifying it as a harness
        failure rather than a product one. Reaching the same conclusion by burning the budget
        costs three more agent turns and three more full suite runs to say it less clearly.
        """
        self.logger.info(
            "the last %s left the QA run failing identically (%s) — escalating instead of "
            "spending another lap",
            lap,
            "; ".join(loop.run_failures),
            extra={"activity": True},
        )
        # The reason travels with the gate for the same purpose it does out of `_exhausted`:
        # in `auto` mode a resolver that escalates ends the story, and the story's marker has
        # to say what ended it. A stall is not a spent budget, so it says so in those words.
        return self._gate(
            result,
            loop.update(
                operator_consulted=True,
                giveup_reason=f"a {lap} that changed nothing",
            ),
        )

    def _guard_plan_validation(
        self, result: object, loop: QaLoop
    ) -> Continue | Await | Done:
        """Spend a schema-validation repair — a budget of its own, not the judgement one.

        A `qa-plan.yml` that does not parse is a mechanical defect, and repairing it says
        nothing about whether the plan tests the story. Charging it to the same ceiling as
        the reviewer let a run of schema typos exhaust the story before any gate had read
        the plan for coverage; `QaLoop.plan_judgement_rework` records the case.

        A parse error is also the most local repair there is, which is why this goes to
        `repair_plan` — regenerating a whole plan to fix an indentation slip threw away a
        correct draft and bought a different one.
        """
        if loop.plan_validation_rework >= self.MAX_PLAN_VALIDATION_REWORKS:
            return self._exhausted(
                loop, f"{loop.plan_validation_rework} QA-plan schema repair"
            )
        return self._plan_lap(
            result, loop.update(plan_validation_rework=loop.plan_validation_rework + 1)
        )

    def _guard_plan_review(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Spend the review component of the QA-plan judgement budget."""
        if loop.plan_judgement_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return self._plan_lap(
            result, loop.update(plan_review_rework=loop.plan_review_rework + 1)
        )

    def _plan_lap(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Take the lap the guard just paid for, unless the plan has had too many in total.

        The three guards above each bound their own stage, and nothing bounded the sum until
        this did. `loop` arrives already incremented, so the ceiling is checked against what
        this lap would make the total — a flow that stops *after* spending its last lap has
        paid for a turn it will not use.
        """
        if loop.plan_rework_total > self.MAX_TOTAL_PLAN_LAPS:
            self.logger.info(
                "the QA plan has had %d repair laps across every gate — ending the flow",
                loop.plan_rework_total - 1,
            )
            return self._exhausted(loop, f"{loop.plan_rework_total - 1} total QA-plan lap")
        return Continue(result, self.repair_plan, loop=loop)

    def _guard_setup(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_setup`: another repair attempt, or the operator gate.

        The budget is not the only thing that ends this loop. A fixer that ran and left the
        runner naming *exactly* the requirements it named before has proved the repair it can
        make does not reach the thing that is broken, and asking it again costs another
        `power="high"` turn under a 2400s timeout to reproduce that. See
        `QaLoop.setup_problems` for the run this comes from.
        """
        if loop.setup_rework >= self.MAX_SETUP_REWORKS:
            return self._exhausted(loop, f"{loop.setup_rework} QA-setup repair")
        if loop.blocked_problems and loop.blocked_problems == loop.setup_problems:
            self.logger.info(
                "the QA setup fix left the identical blocked bundle (%s) — escalating",
                "; ".join(loop.blocked_problems),
                extra={"activity": True},
            )
            return self._gate(
                result,
                loop.update(
                    operator_consulted=True,
                    giveup_reason="a QA-setup repair that changed nothing",
                ),
            )
        return Continue(result, self.setup_fix, loop=loop)

    def _guard_qa(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_qa` + `guard_qa_bonus` + `decide_bonus_class` + `grant_qa_bonus`.

        Past the budget there is exactly one more pass available, and only for an `evidence`
        failure class: the finding is that the proof is missing rather than the code, so one
        verification-only attempt is cheap and often decisive. `code`, `environment` and an
        untriaged blank earn nothing.
        """
        if self._repeating(loop, "code fix"):
            return self._stalled(result, loop, "code fix")
        loop = loop.update(
            repaired_failures=loop.run_failures, repaired_lap="code fix"
        )
        if loop.qa_rework < self.MAX_QA_REWORKS:
            return Continue(result, self.apply_fixes, loop=loop)
        if loop.bonus_used or loop.failure_class != "evidence":
            return self._exhausted(loop, f"{loop.qa_rework} code rework")
        self.logger.info("granting the one verification-only bonus pass")
        return Continue(result, self.apply_fixes, loop=loop.update(bonus_used=True))

    def _fixable(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`decide_qa_fixable`: in a `dev` run the findings are reported, not fixed."""
        if self.target_env == "dev":
            return Continue(result, self.report_dev, loop=loop)
        return self._guard_qa(result, loop)

    def _gate(self, result: object, loop: QaLoop) -> Continue | Await:
        """`gate_qa`: hand the block to the auto-operator, or halt for a human."""
        if self.operator_mode in {"human", "operator"}:
            return Await(self._context, loop.block_notes, self.read_operator, loop=loop)
        return Continue(result, self.resolve_operator, loop=loop)

    def _exhausted(self, loop: QaLoop, spent: str = "") -> Continue | Await | Done:
        """Out of budget — ask the operator once, and only then give up.

        Every deciding site in this flow funnels through here, which is what makes it the
        right place for the ask. A give-up is the flow saying "I have spent everything I am
        allowed to spend", and that is exactly when an operator's one sentence — the port is
        squatted, the driver is fine, this assertion is testing the wrong thing — is worth
        the most. Until this, it was also the one moment the flow stopped asking: eleven
        sites filed the story `exhausted` and only two of them had ever reached the gate.

        The reason is parked on the loop rather than reported (see `QaLoop.giveup_reason`),
        because if the gate does not resolve the block the give-up still has to name the
        budget that actually ran out — not "the operator gate".

        One shot per story: `apply_resolved` has its own `_exhausted`, so without
        `operator_consulted` a guided lap that exhausts again would gate again, forever.
        """
        if not loop.operator_consulted:
            return self._gate(loop, loop.update(operator_consulted=True, giveup_reason=spent))
        return self._give_up(loop, spent or loop.giveup_reason)

    def _give_up(self, loop: QaLoop, spent: str = "") -> Done:
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

        Past the operator gate that is a *pair* of facts, and the first one is the one a
        human triaging the marker needs: which budget ran out originally. The lap the
        operator's answer bought is what happened next, not what the story ran out of, so it
        is reported as the suffix it is rather than as the whole reason.
        """
        spent = spent or loop.giveup_reason
        if loop.giveup_reason and spent != loop.giveup_reason:
            spent = f"{loop.giveup_reason} plus an operator-guided lap"
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
