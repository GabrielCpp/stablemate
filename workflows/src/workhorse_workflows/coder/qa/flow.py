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
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from workhorse.pyflow import AgentTimeout, Await, Continue, Done, Workflow
from workhorse_workflows.coder.shared import paths, qa_support
from workhorse_workflows.coder.shared.backlog import file_backlog_items
from workhorse_workflows.coder.shared.dev import read_operator_context, resolve_impl_context
from workhorse_workflows.coder.shared.docs import detect_okf_docs
from workhorse_workflows.coder.shared.escalation import escalation
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.coder.qa.nodes.evidence import verify_qa_evidence
from workhorse_workflows.coder.qa.nodes.hygiene import check_sentinel_ids, flush_root_screenshots
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.qa.nodes.qa import (
    QA_SCRATCH_DIRNAME,
    clear_qa_evidence,
    ensure_stack,
    lint_qa_plan,
    qa_tools_catalog,
    run_qa_plan,
    validate_qa_plan,
    verify_qa_dry_run,
)
from workhorse_workflows.coder.qa.nodes.regression import (
    detect_regression_platform,
    run_regression_suite,
)
from workhorse_workflows.coder.shared.review import check_feedback
from workhorse_workflows.coder.shared.scenarios import qa_only_scenarios
from workhorse_workflows.coder.shared.story import prepare_story, stamp_specs
from workhorse_workflows.coder.shared.schemas.dev import OperatorGate, OperatorResolution
from workhorse_workflows.coder.shared.schemas.qa import (
    QaAssessment,
    QaAudit,
    QaContextRepair,
    QaFinding,
    QaFlowResult,
    QaLoop,
    QaPlanResult,
    QaReport,
    QaResult,
    QaRunResult,
    QaTriage,
    RegressionFix,
    SetupResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels

UNBOUNDED = float("inf")

#: What the next plan turn is told when the one before it was cut at its wall-clock cap.
#: Prepended to the validation notes by `_validated`, because a truncated `qa_plan.py` is
#: indistinguishable from one whose author made a mistake — and the repair a mistake calls
#: for is a rewrite, which is precisely what must not happen here. Stated as a fact about
#: the *turn*, not as a defect in the file, so the worklist stays "finish it".
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


def _failed_scenario_ids(result: QaRunResult) -> tuple[str, ...]:
    """The ids alone of the scenarios a failing run did not pass, sorted.

    `_failure_signature` above answers a different question with the same payload, and glues
    the status and the assertion counts onto each id to answer it. This is the worklist the
    repair turn is handed and the dry-run gate reads back, so it is the bare ids.

    Empty for every status but `failed`, exactly as the fingerprint is: a `blocked` run never
    reached its scenarios, so there is nothing to demand a dry run of.
    """
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
    """One structured finding as the line whoever repairs it is briefed with.

    Both axes are rendered, because both decide what happened to the finding: `scope` says
    who was billed for it and `kind` says whether it refused the plan. An escalation gate
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

    Every gate — the post-run assessment, the audit — can find a gap whose repair is not the
    plan author's to make. Until this split existed the out-of-scope ones were *dropped*: the
    flow refused to send the author what it may not touch, and then sent the refusal nowhere.
    Audit and assess were free prose, so every refusal they raised landed on the plan author
    regardless.

    That is a livelock, not an inefficiency, and a live story spent 82 minutes in it. Three
    gates each found the same missing assertion in a committed test file, each billed the one
    author who cannot write one, and each got back a plan that disclosed the gap again.
    """

    plan: list[QaFinding]
    product_test: list[QaFinding]
    stack: list[QaFinding]


def _route_findings(findings: Sequence[QaFinding]) -> RoutedFindings:
    """Partition findings by `scope` — the closed vocabulary is what makes this decidable.

    The boundary the gates' briefs state in prose — the heavyweight shared stack belongs to
    `ensure_stack`, a repair the author cannot make inside a plan file spends the budget and
    returns the same worklist next pass — is one real runs cross anyway. Prose in a brief is
    not a filter and free-form `notes` left the flow nothing to filter *with*; a closed
    `scope` on each finding does.
    """
    return RoutedFindings(
        plan=[finding for finding in findings if finding.scope == "plan"],
        product_test=[finding for finding in findings if finding.scope == "product-test"],
        stack=[finding for finding in findings if finding.scope == "stack"],
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
    #: The lane's wall-clock budgets, in seconds of agent turns — **advisory**. Crossing one
    #: is logged and nothing else: it never ends a story, never demotes a repair to a re-run,
    #: and never lets an unresolved audit refutation through as backlog work. Only the lap
    #: ceilings below can end a QA loop.
    #:
    #: They were terminal, and that is the defect this replaced. A wall clock cannot tell a
    #: loop that is going nowhere from one that is three turns from green, so it cut both the
    #: same way — and what it cut was disproportionately the stories doing the *most* real
    #: repair work, because those are the ones that spend. Two live stories reached a green
    #: 41/41 runner and were still stamped "QA FAILED — needs manual review" with their
    #: dependents blocked, because the clock expired before the four post-run gates had
    #: signed off. A lap ceiling says "this was tried the agreed number of times", which is
    #: a statement about the work; a clock says only that the work was slow.
    #:
    #: Kept as `--param` fields, and not deleted, because the number is still the honest
    #: signal an operator wants in the log and in telemetry — a story that ran 3× its budget
    #: is worth looking at, just not worth discarding. Fields and not `ClassVar`s like the
    #: lap budgets below for the same old reason: those are invariants of the flow's shape,
    #: while "a story's QA should fit in an hour" is a per-run policy that lands in the
    #: checkpoint. `ensure_stack` is outside both (see `QaLoop.lane_seconds`), as are
    #: `resolve_operator`, `apply_feedback` and `report_dev`.
    qa_lane_budget_s: int = 3300
    plan_lane_budget_s: int = 2400
    #: The CLI session id to resume for the story's backbone turns, threaded in from a
    #: prior stage's turn across a `handoff()` boundary. Empty starts a fresh chain.
    session_id: str = ""

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: The bounded retry budgets. All `ClassVar`, because none of them is a var the YAML
    #: declared — each guard carries a branch literal. See the module docstring.
    #:
    #: These are now the *only* things that can end a QA loop short of a verdict, so they
    #: carry weight the wall clock used to share. They were sized against a lane that would
    #: be cut off by the clock anyway, which made a generous ceiling meaningless; with the
    #: clock advisory, the ceiling is the whole policy and the code-fix one is raised from
    #: three to eight. A code fix is the lap most likely to be *working* — each one is a
    #: named failing check against a green-when-fixed suite — and three of them is well
    #: inside the range where a story is still converging.
    MAX_QA_REWORKS: ClassVar[int] = 8
    MAX_CONTEXT_REWORKS: ClassVar[int] = 3
    #: Trips through the gate that get a resolver turn before every further block goes
    #: straight to a human — the same shape `dev`'s `MAX_PLAN_BLOCKS` and `review`'s
    #: `MAX_REVIEW_BLOCKS` have, and it became load-bearing the moment the resolver was
    #: allowed to *answer*. An escalating resolver bounds itself: the `Await` underneath it
    #: is what ends the lap. An answering one hands the flow straight back to
    #: `read_operator`, so a block whose answer does not clear the underlying failure
    #: returns to this gate unchanged and is answered again, forever, with no human ever
    #: reached. This is not a cap on how many times QA may block — there is none, and the
    #: budget is spent on an answer exactly as it is on an escalation, so a resolver that
    #: keeps answering the same block walks toward a person rather than lapping behind one.
    MAX_QA_BLOCKS: ClassVar[int] = 3
    #: The two QA-plan budgets are deliberately separate. `MAX_PLAN_REWORKS` bounds the
    #: gates that judge the plan (the post-run assessment and the audit);
    #: `MAX_PLAN_VALIDATION_REWORKS` bounds repairs of a `qa_plan.py` that does not import.
    #: See `QaLoop.plan_judgement_rework` for the story that split them.
    #:
    #: The judgement budget was cut to three when a spent plan-lane clock would demote the
    #: plan to the runner anyway — running a slightly worse plan beat spending the lane's
    #: whole wall clock on judgement, since the plan nodes were 1527 of a QA lane's ~1800
    #: minutes against 2.9% for actually running the plan. That demotion is gone with the
    #: clock, so the trade is no longer "one more lap versus a run"; it is "one more lap
    #: versus no verdict". Raised to six. Every one of these laps buys a repair of a plan
    #: that has actually been *executed*.
    #: `MAX_PLAN_VALIDATION_REWORKS` is left alone: a `qa_plan.py` that will not import
    #: cannot be run *at all*, so those laps are not a quality trade, and each is `power="low"`.
    MAX_PLAN_REWORKS: ClassVar[int] = 6
    MAX_PLAN_VALIDATION_REWORKS: ClassVar[int] = 3
    #: And the ceiling on their *product*. The two budgets above are spent independently, so
    #: nothing stopped a story alternating between them: three schema repairs and four
    #: judgement repairs is seven laps that every individual guard considers legal, and a
    #: live story reached thirteen turns of `plan-qa` that way. This bounds the sum, so the
    #: stacked budgets can no longer multiply.
    #:
    #: It is a *sum* and not a product, which is the whole point. Two constraints fix it.
    #: Below, it must leave room for three schema repairs and two blocking audits to all be
    #: legal — a ceiling under five lets a run of typos starve the reader, which is what
    #: `test_schema_repairs_cannot_starve_the_semantic_plan_gate` exists to catch. Above, it
    #: must stay under `MAX_PLAN_REWORKS + MAX_PLAN_VALIDATION_REWORKS`, or it is inert: at
    #: the stacked maximum no interleaving can ever reach it. It rose from five with
    #: `MAX_PLAN_REWORKS`, to one below that stacked maximum of nine. The lane's wall clock
    #: is held by the per-turn caps on the three plan nodes, not here.
    MAX_TOTAL_PLAN_LAPS: ClassVar[int] = 8
    #: Not a spend ceiling — a *blocking* ceiling, and the only one of these that changes what
    #: a finding means rather than how many are affordable. Nothing stands downstream of the
    #: audit, so a plan-scoped refutation it raises can only be closed by another plan repair,
    #: and the
    #: auditor samples the riskiest evidence rather than enumerating everything — which means
    #: each repair is judged against a bar that moves. A live story died of exactly that: three
    #: audits, three *different* genuine gaps, each closed, the fourth lap out of budget and
    #: escalated a plan whose runner had passed every time. Past this many
    #: plan-scoped refutations the audit stops blocking: its findings still get written and
    #: filed as backlog work, and the story lands on the verdict its evidence supports.
    #: Product contradictions and findings whose repair is a test or the stack are unaffected
    #: — those route to loops with ceilings of their own.
    MAX_BLOCKING_AUDITS: ClassVar[int] = 2
    MAX_SETUP_REWORKS: ClassVar[int] = 2
    MAX_REGRESSION_FIXES: ClassVar[int] = 3
    MAX_TRIAGE_SCOPES: ClassVar[int] = 2
    #: How many consecutive laps `repair_plan` may spend on one session chain before it
    #: starts a fresh conversation. Continuity is what stops each lap re-deriving the plan it
    #: is editing, but a conversation that has been wrong four times running is no longer a
    #: head start — it is a transcript of four rejected repairs, and the compaction that keeps
    #: it in the window summarises the wrong turns as readily as the right ones.
    MAX_CHAIN_LAPS: ClassVar[int] = 4

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its `qa/` directory."""
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    @property
    def _chain(self) -> str:
        """The session chain `repair_plan` runs on, keyed per story.

        Per story and not per run: two stories QA'd by the same run repair two different
        plans against two different diffs, and sharing one conversation would open the second
        on the first one's worklist.
        """
        return f"qa-plan-repair:{self.ctx.story_slug}"

    def _story_chain(self) -> str:
        """The backbone conversation this story's primary turns run on.

        An incoming session id (threaded from a prior stage across a handoff boundary) is
        resumed directly; otherwise a fresh per-story chain is named and the CLI mints one
        the first time it is used. Distinct from `_chain`/`_WORKLISTS`: those name the
        narrower, intentionally-isolated repair loops, and stay untouched by this one.
        """
        return self.session_id or f"story:{self.ctx.story_slug}"

    #: The repair loops that run on a chain of their own, as the worklist half of their key.
    #: `fix_regression` builds its this way; the plan-repair chain is `_chain`, which several
    #: states reset on its own. The fix loop is deliberately absent: it runs on the story's
    #: backbone chain (`_story_chain()`) rather than a private one — see `_apply_fixes`.
    _WORKLISTS = ("plan-repair", "feedback", "regression-fix")

    def _reset_chains(self) -> None:
        """Drop every chain this flow opens for the current story."""
        for worklist in self._WORKLISTS:
            self.reset_session(f"qa-{worklist}:{self.ctx.story_slug}")

    def _ends(self, result: QaFlowResult) -> Done:
        """End the flow, and every chain it opened with it.

        A chain outliving its flow is the failure this exists to prevent: the run moves to
        the next story, that story's QA opens `qa-plan-repair:<its slug>` — a different key,
        so it is safe — but a *re-QA* of this same story would otherwise resume a
        conversation about a plan and a diff that have both moved on since.
        """
        self._reset_chains()
        result.session_id = self._require_engine().session_id(self._story_chain())
        return Done(result)

    #: `ensure_stack` brings a durable app stack up and health-gates it — on a real run
    #: that is minutes of `booting app: … waiting up to 2400s`, and it is the model
    #: sitting idle, not working. Marking it keeps a slow stack out of any aggregate
    #: that would otherwise read the wait as effort.
    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack})

    #: The budgets worth grouping a query by. Every one of `QaLoop`'s counters, because
    #: this flow's whole shape is which of them ran out first — `audit_rework` included,
    #: which is not a spend counter but answers the same question about the last gate.
    #:
    #: `QaLoop.lane_seconds` and `plan_lane_seconds` are deliberately *not* here. Every
    #: agent turn is already a span with its own duration, so what they hold is a sum a
    #: query reconstructs — and the lane's own wall clock is the `state:qa` span. They exist
    #: because the flow has to read them at a transition, where it cannot query anything;
    #: labelling them would spend cardinality restating what the spans already say.
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
        # A re-QA of a story that was already QA'd — after a fix, after an operator answer,
        # after a resume — must not resume the previous pass's repair conversation: it
        # describes a plan and a diff that have both been rewritten since.
        self._reset_chains()
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
        # The join point ends the repair chain for the same reason it clears `plan_authored`
        # below: every state that routes back here changed what the diff obligates, so the
        # conversation that was repairing the old plan is now describing the wrong file.
        self.reset_session(self._chain)
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
            # Zeroed with the chain itself, so the next chain gets a whole budget rather than
            # inheriting a count of laps that belonged to a conversation that no longer exists.
            chain_laps=0,
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
        started = time.monotonic()
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
        loop = (
            loop.charged(time.monotonic() - started)
            .require_docs_recheck()
            .with_qa(reply.qa_result)
        )
        if reply.qa_context_repair.status == "repaired":
            return Continue(
                reply, self.build_context, loop=loop.update(context_rework=loop.context_rework + 1)
            )
        return self._gate(reply, loop)

    # ── plan ──────────────────────────────────────────────────────────────────────────

    def plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Author the QA plan, forget every previous gate's findings, and parse the result.

        `plan_qa` + `clear_qa_gate_state` + `stamp_specs_qa_plan` + `lint_qa_plan` +
        `validate_qa_plan` + `decide_qa_plan_validation`.

        The plan turn is handed every diagnostic the loop collected — the packet's status,
        the last validation, the last run assessment, the last audit, the last evidence
        verdict — and then those are cleared, because they describe a plan that no longer
        exists. `validate_qa_plan` immediately writes a fresh one.

        This state is the *first draft only*. Every later lap — a schema defect, a post-run
        finding, an audit refutation — goes to `repair_plan`, which edits the plan instead of
        writing a new one.

        The turn's *reply* is discarded but for one field — the deliverable is `qa_plan.py`
        on disk, which the validation tail reads back. That is what makes a turn cut at its
        20-minute cap survivable, and it is the whole reason for `retries=0` plus the catch
        below. `status` is the exception, because it is a claim about the turn rather than
        about the file: a planner that says it cannot write a plan for this story has written
        no file for the tail to read, and every validation-repair lap after it is spent
        discovering that.
        """
        self.logger.info("planning QA for %s", self.ctx.story_slug, extra={"activity": True})
        overran = ""
        started = time.monotonic()
        drafted: QaPlanResult | None = None
        try:
            drafted = self.agent(
                "prompts/plan-qa.md",
                returns=QaPlanResult,
                # medium: writing a runnable plan against a schema, from a story and an
                # obligation packet that both already exist.
                power="medium",
                session=self._story_chain(),
                # 20 min. Without a cap this node inherits the run's 3600s watchdog, and it
                # used it: over four days its longest turns were exactly 60.0 min, and two
                # thirds of the whole node's wall clock was spent past the 15-min mark by the
                # minority of turns that ran long. Fifty of sixty-five finished inside 20.
                timeout=1200,
                # A reframe would throw the draft away and re-author from nothing, at the
                # authoring tier and for another 20 minutes — three times over before the run
                # stops. `repair_plan` keeps the draft and costs a fifth as much, so the cut
                # turn is worth more to this flow than any number of fresh ones.
                retries=0,
                add_dirs=self._dirs(),
                args=self._plan_args(loop),
            )
        except AgentTimeout:
            self.logger.info(
                "the QA-plan turn was stopped at its budget — validating what it wrote",
                extra={"activity": True},
            )
            overran = _OVERRAN_PLAN
        loop = loop.charged(time.monotonic() - started, plan=True)
        if drafted is not None and drafted.blocked:
            return self._refused(drafted, loop, "the QA planner")
        return self._validated(loop, overran=overran)

    def repair_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """Edit the cited part of a plan that already exists, leaving the rest byte-identical.

        Every lap after the first used to re-enter `plan`, which regenerates the whole file
        from the story. That **resamples the scenarios the reviewer already accepted**, so
        each pass handed the gate a fresh set of defects to find and the loop had no reason
        to terminate — `plan-qa` averaged 5.5 turns per story and reached 13, with the same
        demand refused pass after pass. Repairing only what was cited makes the worklist
        shrink monotonically, which is the whole mechanism by which the loop converges.

        It takes the same brief as `plan` and returns the same result, so the validation tail
        and every guard are unchanged; what differs is the instruction, the power tier and
        the dry run. The turn has the stack up and the plan on disk, so it is told to execute
        each failing scenario itself — `ostler qa run … --scenario <id> --out-dir
        <id>`, which lands in `qa/<id>/` — and `verify_qa_dry_run` reads that scratch
        evidence back before
        the flow spends a whole suite run finding out. A repair that has not been observed to
        work is a hypothesis, and this lane was paying a full run per hypothesis.

        Every lap runs on one session chain, so the turn that is handed "scenario 4 still
        fails" is the turn that wrote scenario 4 and remembers why. The chain is dropped when
        continuity stops being worth its length: after `MAX_CHAIN_LAPS` consecutive laps, on a
        lap that already failed at exactly what the last one failed at, and at every rejoin
        through `build_context` — which is also where the counter is zeroed.
        """
        self.logger.info("repairing the QA plan for %s", self.ctx.story_slug,
                         extra={"activity": True})
        laps = loop.chain_laps
        if laps >= self.MAX_CHAIN_LAPS or self._repeating(loop, "QA-plan repair"):
            self.reset_session(self._chain)
            laps = 0
        loop = loop.update(chain_laps=laps + 1)
        overran = ""
        repaired: tuple[str, ...] = ()
        result: QaPlanResult | None = None
        started = time.monotonic()
        try:
            result = self.agent(
                "prompts/repair-qa-plan.md",
                returns=QaPlanResult,
                # low: applying a named list of edits to a file that already exists is not
                # the work that authoring the plan was, and paying the authoring tier for it
                # is what tempted the turn to rewrite rather than repair.
                power="low",
                # 45 min. The old 15 was sized for "apply a worklist", which averages five —
                # but the turn now also drives the stack and dry-runs every failing scenario
                # through `ostler qa run`, and one browser scenario alone can spend minutes.
                # Cutting it at 15 stopped the turn between the edit and the evidence, which
                # is the one place its work is worth least.
                timeout=2700,
                # Same reasoning as `plan`: the file on disk is the deliverable, and a repair
                # that got halfway is a better starting point than a fresh session that has
                # to re-read the worklist from the top. `MAX_PLAN_VALIDATION_REWORKS` and
                # then `MAX_TOTAL_PLAN_LAPS` are what bound a plan that cannot be finished.
                retries=0,
                add_dirs=self._dirs(),
                args=self._plan_args(loop),
                session=self._chain,
            )
            repaired = tuple(str(scenario) for scenario in result.repaired_scenarios)
        except AgentTimeout:
            self.logger.info(
                "the QA-plan repair turn was stopped at its budget — validating what it wrote",
                extra={"activity": True},
            )
            overran = _OVERRAN_REPAIR
        loop = loop.charged(time.monotonic() - started, plan=True)
        if result is not None and result.blocked:
            # Every lap here is a *repair*, so the scenario it could not repair is the same
            # one the next lap would be handed. The validation tail would find the plan still
            # red, the guard would grant another lap, and the chain would keep the same
            # refusal in its own context — which is the loop this branch exists to leave.
            return self._refused(result, loop, "the QA-plan repair")
        return self._validated(
            loop,
            overran=overran,
            dry_run=tuple(sorted({*loop.failed_scenarios, *repaired})),
        )

    def _plan_args(self, loop: QaLoop) -> dict[str, object]:
        """Every diagnostic the loop collected, for whichever plan turn is about to run.

        Plus what the *dev* lane already resolved about the surface. `plan-context.json`
        carries the stack profile, the fixture files and a prose description of what the
        running surface renders, all of it vetted by `ostler artifact vet plan-context` — and
        until now it reached exactly one QA prompt, `setup-fix.md`, which runs only after a
        run is already blocked. The planner was left re-deriving a fixture path that was
        sitting in a file two directories up, and getting it wrong is how a scenario comes
        back `blocked` on data that exists.

        `failed_scenarios` is the repair turn's contract, not a diagnostic: each entry is a
        scenario the last run did not pass, with the ids of its FAIL assertions read off the
        runner's own log. The prompt turns the list into a demand — dry-run each of these
        until it passes — and `verify_qa_dry_run` checks it was met. It is empty for the
        `plan` turn and after any run that did not fail, which is what makes the same brief
        serve both nodes.

        `qa_scratch_dir` is the other half of the dry run. It is `qa_dir` itself, because a
        dry run writes a subdirectory of it: that is the one directory a repo ignores, and
        the sibling layout it replaces shipped hundreds of megabytes of traces into client
        repos. Nesting takes nothing away — `verify_qa_evidence` names `qa/qa-run.ndjson` and
        `qa/run-manifest.json` by exact path, so a scenario tuned until it passed still
        cannot leave its own admissible evidence, and `clear_qa_evidence` wiping `qa/` whole
        now removes the scratch with it.

        `qa_only_scenarios` is the dev plan's own list of what it decided *not* to write a
        test for. The dev lane's red gate reads the same section to decide whether to run
        the tests-first split at all; passing the QA-only subset here is the other half of
        that decision, because a scenario excluded from the suite and handed to nobody is
        covered by nothing in the run. They arrive as data — title, AC, level — so the
        planner turns each into an obligation rather than re-deriving the list by reading.
        """
        impl = self.output(resolve_impl_context)
        tools = self.call(qa_tools_catalog, self.docs_path)
        spec_abs = Path(self.ctx.spec_dir) if self.ctx.spec_dir else None
        failed_assertions = (
            qa_support.failed_assertions(qa_support.scored_run_log(spec_abs))
            if spec_abs and loop.failed_scenarios
            else {}
        )
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "qa_dir": self.ctx.qa_dir,
            "qa_scratch_dir": QA_SCRATCH_DIRNAME,
            "docs_path": self.docs_path,
            "target_env": self.target_env,
            "qa_stack": impl.qa_stack,
            "shared_packages": impl.shared_packages,
            "qa_only_scenarios": [
                {"title": s.title, "ac": s.ac, "level": s.level}
                for s in qa_only_scenarios(spec_abs, "")
            ],
            "failed_scenarios": [
                {"id": scenario, "failed_assertions": failed_assertions.get(scenario, [])}
                for scenario in loop.failed_scenarios
            ],
            "context_status": loop.context_status,
            "context_notes": loop.context_notes,
            "plan_validation_notes": loop.plan_validation_notes,
            "run_assessment_notes": loop.assessment_notes,
            "audit_notes": loop.audit_notes,
            "evidence_notes": loop.qa.notes,
            "qa_tools": tools.tools,
        }

    def _validated(
        self, loop: QaLoop, overran: str = "", dry_run: tuple[str, ...] = ()
    ) -> Continue | Await | Done:
        """The tail both plan turns share: clear the brief, stamp, parse, route on the parse.

        A plan that parses goes straight to the runner. There is no semantic pre-run gate
        any more: what the reviewer used to judge — does this plan actually test the story —
        is now decided by the book. `ostler qa lint` runs first and rejects a plan whose AST
        reaches outside the allowlist before anything imports it; every obligation carries the
        `verify:` check the node declared, `ostler qa validate` refuses a plan that claims an
        obligation without invoking that call with those arguments, and `ostler qa
        evidence-map` reports the deficit after the run. A `power="high"` turn re-deriving
        that by reading is the most expensive node in the lane and, per the corpus replay,
        accounted for 78 of its 79 blocking findings from checks the machine now performs.

        `overran` is set when the turn that just ran was cut at its wall-clock cap. It is
        prepended to the validation notes so the repair turn is *told* the file is a draft
        someone stopped mid-sentence, rather than left to infer it from a truncated file —
        which reads exactly like a plan whose author made a mistake, and invites a rewrite.
        It is only ever a brief: a plan that validates goes to the runner regardless, because
        a plan that parses is a plan that runs whatever cut its author short.

        `dry_run` is the one thing the two turns do not share. A repair is dispatched against
        a named set of failing scenarios, so it can be *asked to prove it worked* before the
        suite is spent finding out — which is what `verify_qa_dry_run` reads. The `plan` turn
        has no failing set to prove anything about and passes nothing here, so the gate is
        skipped rather than vacuously passed.
        """
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
                    "the QA-plan repair did not dry-run clean — repairing again without "
                    "spending a suite run",
                    extra={"activity": True},
                )
                return self._guard_dry_run(
                    gate, loop.update(plan_validation_notes=_finding(False, gate.notes))
                )
        return Continue(validation, self.run, loop=loop.update(plan_authored=True))

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

        Which makes this an entry into the plan lane, bounded like every other one by
        `MAX_CONTEXT_REWORKS` — a rejoin costs a context rebuild, and those are counted.
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
            # `build_context` clears `plan_authored`, so every rejoin from a context rebuild —
            # an `apply_fixes` lap, a grounding repair — buys a fresh `power="high"` authoring
            # turn. What bounds that is `MAX_CONTEXT_REWORKS`, the ceiling on the rebuilds
            # themselves, not the clock: a rejoin cannot happen without one.
            self._note_plan_budget(loop)
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
        handed. See `QaLoop.repaired_failures`. The bare ids go alongside it: they are the
        set the next repair turn must dry-run before the suite is spent on it again.
        """
        self.logger.info("running the QA plan", extra={"activity": True})
        result = self.call(
            run_qa_plan, self.ctx.spec_dir, self.docs_path, manifest_path=self.qa_stack_manifest
        )
        return Continue(
            result,
            self.assess,
            loop=loop.with_qa(result).update(
                blocked_problems=_blocked_problems(result),
                run_failures=_failure_signature(result),
                failed_scenarios=_failed_scenario_ids(result),
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
        started = time.monotonic()
        assessment = self.agent(
            "prompts/qa-story.md",
            returns=QaAssessment,
            # medium: judging a runner's output against a plan that already passed two
            # gates. The adversarial read is `audit_qa`'s job, at high.
            power="medium",
            session=self._story_chain(),
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
        if assessment.blocked:
            # Ahead of the dispositions, because a turn that could not read the run has no
            # standing to classify it — and `repair_plan`, the default a silent reply takes,
            # would bill the plan author for a judgement nobody made.
            return self._refused(assessment, loop.charged(time.monotonic() - started),
                                 "the QA run assessment")
        loop = loop.charged(time.monotonic() - started).update(
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
        started = time.monotonic()
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
        if result.blocked:
            # `refuted` is a verdict about the evidence; this is the auditor saying there was
            # nothing it could judge. Defaulting one into the other spends a plan rework on a
            # refutation that was never made.
            return self._refused(result, loop.charged(time.monotonic() - started),
                                 "the QA audit")
        loop = loop.charged(time.monotonic() - started).update(
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
        loop = loop.update(audit_rework=loop.audit_rework + 1)
        elsewhere = self._routed(result, loop, result.findings, result.notes)
        if elsewhere is not None:
            return elsewhere
        if loop.audit_rework > self.MAX_BLOCKING_AUDITS:
            self.logger.info(
                "the audit has refuted this pass %d times with plan-only findings — filing "
                "this one as backlog work rather than spending another plan repair",
                loop.audit_rework,
                extra={"activity": True},
            )
            return Continue(result, self.backlog, loop=loop)
        self._note_lane_budget(loop)
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
        started = time.monotonic()
        triage = self.agent(
            "prompts/triage-qa.md",
            returns=QaTriage,
            # medium: sorting findings into in-AC and adjacent, against a story whose ACs
            # are written down.
            power="medium",
            session=self._story_chain(),
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
        if triage.blocked:
            # Both defaults below are classifications, and a triager that could not sort the
            # findings has made neither. Taking one anyway sends the story to a loop on the
            # strength of a verdict nobody reached.
            return self._refused(triage, loop.charged(time.monotonic() - started),
                                 "the QA triage")
        loop = loop.charged(time.monotonic() - started).update(
            failure_class=triage.qa_failure_class
        )
        if loop.triage_scope >= self.MAX_TRIAGE_SCOPES:
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

    def report_dev(self, loop: QaLoop) -> Done:
        """`target_env=dev`: we do not own the code, so write the findings out and stop.

        `report_qa_dev` + `mark_qa_exhausted`. The `inconclusive` default status is not a
        judgement on the report — it is how the parent's `decide_qa_fail` learns the story
        did not pass. This is the one legitimate terminal exit left in this flow: a dev
        target has no code to rework, so there is no operator-answerable question to gate on.
        """
        report = self.agent(
            "prompts/report-qa-dev.md",
            returns=QaReport,
            # medium: summarising findings that are already written down, into a tracker.
            power="medium",
            session=self._story_chain(),
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.qa.notes,
            },
        )
        if report.blocked:
            # Advisory, deliberately: the findings are already written down in `qa_dir`, and
            # this turn only summarises them into a tracker. Gating a `dev` run's terminal
            # act on the summary would park a story whose actual output already landed.
            self.logger.warning(
                "the QA report turn reported it could not write the summary (%s) — the "
                "findings themselves are already in %s",
                report.notes or "no reason given", self.ctx.qa_dir,
            )
        self.logger.info("QA findings reported: %s", report.notes)
        return self._ends(
            QaFlowResult(
                qa=loop.qa,
                qa_rework=loop.qa_rework,
                triage_scope=loop.triage_scope,
                docs_recheck_required=loop.docs_recheck_required,
            )
        )

    # ── the passing path: feedback, regression, sentinels ─────────────────────────────

    def feedback(self, loop: QaLoop) -> Continue:
        """Poll the run's inbox once before believing the pass.

        `check_qa_feedback` + `decide_qa_feedback`. Never halts and never asks: polling the
        inbox replies to the oldest outstanding message, so one dropped note buys exactly
        one re-QA.
        """
        note = self.call(check_feedback, str(self.run_dir))
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
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes="",
            operator_feedback=content,
            power="medium",
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
        claim of *success* is not read — the re-run is the verdict. Its claim that it cannot
        get there is, because the re-run cannot express it: a suite that is still red looks
        the same whether the last turn ran out of ideas or never had any, so the loop grants
        another lap and spends a 90-minute turn on the question it just answered.
        """
        platform = self.output(detect_regression_platform)
        run = self.output(run_regression_suite)
        self.logger.info("fixing the regression suite", extra={"activity": True})
        started = time.monotonic()
        fix = self.agent(
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
            # Lap two is handed the same suite, still red, and its first act on a fresh
            # context is to re-reproduce the failure lap one had already reproduced — a
            # twenty-five-minute suite run spent re-learning what it just knew.
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
        return self._ends(
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
            session=self._story_chain(),
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "qa_dir": self.ctx.qa_dir,
                "qa_notes": loop.block_notes,
            },
        )
        return self._ends(
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
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes=loop.qa.notes,
            operator_feedback=None,
            power="high",
            session=self._story_chain(),
        )
        loop = loop.charged(time.monotonic() - started).update(
            qa=result, qa_rework=loop.qa_rework + 1, docs_recheck_required=True
        )
        if result.blocked:
            # The derived signal, not the literal `"blocked"`: this prompt's own reply has
            # come back `unfixable` and `not_passed` as often as `blocked`, and three
            # quarters of one vocabulary fell through to another lap of the same loop.
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
        started = time.monotonic()
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
                # The interpreter the QA runner's pre-flight actually checks: the QA nodes
                # import the runner as a library, so a requirement like "requires the Playwright
                # Python package" is a statement about *this* process. A fixer told only to
                # install the package repairs whichever copy `pip`/`uv tool` happens to reach,
                # reports `ready`, and the next run comes back blocked on the same bundle.
                "runtime_python": sys.executable,
            },
        )
        loop = loop.charged(time.monotonic() - started).update(
            setup_rework=loop.setup_rework + 1,
            docs_recheck_required=True,
            # What this turn was asked to repair, for the next `_guard_setup` to compare the
            # next blocked run against.
            setup_problems=loop.blocked_problems,
        )
        if result.blocked:
            return self._gate(result, loop)
        return Continue(result, self.stack, loop=loop)

    # ── the operator gate ─────────────────────────────────────────────────────────────

    def resolve_operator(self, loop: QaLoop) -> Continue | Await:
        """Resolve a QA block from what is already written down, or park the run for a human.

        The narrowest of the four lanes, deliberately. The resolver may answer a QA block
        the way it answers any other — by quoting the decision record, rule or acceptance
        criterion that settles it — but the resolutions *in its own favour* stay forbidden
        whatever it can cite: it may not narrow the plan's `covers:` to make a gap
        uncovered-and-fine, stamp the story's status, edit `qa-evidence.json`, or offer a
        test suite as evidence about the product. Those are the ones this loop exists to
        keep out of its hands, and the prompt names them. It also still cannot decide the
        story is unrecoverable — a workflow does not give up, it blocks.

        `resolve_qa` + the `await_operator_qa` that followed it, folded into one turn.
        """
        self.logger.info("diagnosing the QA block for the operator", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: a full-tool-access investigation ahead of the highest-
            # stakes decision in the flow.
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
        # `Await` writes its `questions` over this file with `write_text`, so the body it is
        # handed has to *contain* the note the resolver just wrote there — which is what
        # `_escalation` does, on top of saying what was tried and what would unblock it.
        gate = self._escalation(loop, result)
        return Await(self._context, gate.body, self.read_operator, loop=loop)

    def read_operator(self, loop: QaLoop) -> Continue | Done:
        """Consume the answer and route on the scope the answerer chose.

        `await_operator_qa`'s consume half + `decide_operator_scope_qa`. An `epic`-scoped
        answer says the premise was wrong, which no amount of QA fixing reaches — the parent
        graph re-derives the epic from it.
        """
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
        started = time.monotonic()
        result = self._apply_fixes(
            qa_notes=loop.qa.notes,
            operator_feedback=content,
            power="medium",
            session=self._story_chain(),
        )
        loop = loop.charged(time.monotonic() - started).update(
            qa=result,
            qa_rework=loop.qa_rework + 1,
            docs_recheck_required=True,
        )
        if result.blocked:
            # Ahead of the budget check, and it is not the same escalation: the fixer was
            # handed the operator's own answer and still says it cannot get there, which
            # means the answer did not reach the block. Going round for another lap re-runs
            # a fix against an instruction already known not to work.
            return self._refused(result, loop, "the operator-guided QA fix")
        if loop.qa_rework >= self.MAX_QA_REWORKS:
            self.logger.info("operator-guided rework loop is out of QA reworks — escalating")
            return self._exhausted(loop, f"{loop.qa_rework} operator-guided rework")
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
            loop.with_lap(
                "QA-plan repair",
                plan_rework=loop.plan_rework + 1,
                repaired_failures=loop.run_failures,
            ),
        )

    def _guard_dry_run(self, gate: object, loop: QaLoop) -> Continue | Await | Done:
        """A repair whose own dry run refused it — repair again, on the same budget.

        The judgement budget and not a new one: the lap is a QA-plan repair lap whichever
        gate refused it, and a dry-run failure is the *cheap* way to learn what the post-run
        gate would have said an hour later. Adding a budget here would let a story spend
        more laps than before by failing earlier in each of them.

        `_repeating` is deliberately not consulted, which is the one difference from
        `_guard_plan`. That detector asks whether the last repair left *the suite* failing
        identically, and its inputs are a run fingerprint; no run happened between this
        repair and this refusal, so the fingerprint is the one the previous guard already
        stamped and the test would report a stall on every first dry-run failure. The
        sameness signal still fires where it means something — after the next scored run.
        """
        if loop.plan_judgement_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop, f"{loop.plan_judgement_rework} QA-plan repair")
        return self._plan_lap(
            gate,
            loop.with_lap(
                "QA-plan repair",
                plan_rework=loop.plan_rework + 1,
                repaired_failures=loop.run_failures,
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

        But "not repairable from where we are repairing it" is an argument for repairing it
        somewhere else, and only after that for ending the story — so the untried class goes
        first. See `_switched`.
        """
        other = "code fix" if lap == "QA-plan repair" else "QA-plan repair"
        if not loop.class_switched and other not in loop.tried_laps:
            return self._switched(result, loop, lap, other)
        self.logger.info(
            "the last %s left the QA run failing identically (%s) — escalating instead of "
            "spending another lap",
            lap,
            "; ".join(loop.run_failures),
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
        """A repair that moved nothing refutes the *hypothesis*, not the story.

        `_repeating` is a correct budget signal and a wrong diagnosis. "The QA-plan repair
        changed nothing" is evidence that the failure is not in the plan, and that is an
        argument for looking at the product — not for ending the story. A live story was
        abandoned into `qa-skip-stories.txt` on exactly that inference having spent zero code
        laps, and the five assertions it died on were races in the plan.

        One switch per story, and only toward a class that has never run. That is the whole
        termination argument: `QaLoop.class_switched` is monotone and written only here, both
        exits below charge a counter with its own ceiling, and the second stall — whichever
        class raises it — falls straight through to the gate above.

        `_fixable` and not `apply_fixes`: a `dev` run reports findings rather than editing
        code it does not own, and that is not a rule this shortcut gets to skip.
        """
        self.logger.info(
            "the %s left the QA run failing identically (%s) — trying a %s before the "
            "operator, because a repair that moved nothing refutes the hypothesis class",
            spent,
            "; ".join(loop.run_failures),
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
        """Spend a schema-validation repair — a budget of its own, not the judgement one.

        A `qa_plan.py` that does not import is a mechanical defect, and repairing it says
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
            result,
            loop.update(plan_validation_rework=loop.plan_validation_rework + 1),
        )

    def _plan_lap(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """Take the lap the guard just paid for, unless the plan has had too many in total.

        The three guards above each bound their own stage, and nothing bounded the sum until
        this did. `loop` arrives already incremented, so the ceiling is checked against what
        this lap would make the total — a flow that stops *after* spending its last lap has
        paid for a turn it will not use.

        The lap count is the only ceiling here. `plan_lane_budget_s` used to be a second one,
        which is what let a plan lane that was still making progress be cut off mid-repair;
        it is now advisory and only logged. See `_note_plan_budget`.
        """
        self._note_plan_budget(loop)
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
        self._note_lane_budget(loop)
        if loop.blocked_problems and loop.blocked_problems == loop.setup_problems:
            self.logger.info(
                "the QA setup fix left the identical blocked bundle (%s) — escalating",
                "; ".join(loop.blocked_problems),
                extra={"activity": True},
            )
            return self._gate(result, loop)
        return Continue(result, self.setup_fix, loop=loop)

    def _guard_qa(self, result: object, loop: QaLoop) -> Continue | Await | Done:
        """`guard_qa` + `guard_qa_bonus` + `decide_bonus_class` + `grant_qa_bonus`.

        Past `MAX_QA_REWORKS` there is exactly one more pass available, and only for an
        `evidence` failure class: the finding is that the proof is missing rather than the
        code, so one verification-only attempt is cheap and often decisive. `code`,
        `environment` and an untriaged blank earn nothing.
        """
        if self._repeating(loop, "code fix"):
            return self._stalled(result, loop, "code fix")
        loop = loop.with_lap("code fix", repaired_failures=loop.run_failures)
        self._note_lane_budget(loop)
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

    def _refused(self, result: CoderResult, loop: QaLoop, what: str) -> Continue | Await:
        """A turn that said it cannot get there, handed straight to the operator.

        Every lane node routes its refusal through here rather than through the budget guard
        beside it. The guard's question is "has this loop had enough tries", and the answer
        it gets from a turn that just said the work is not doable is the wrong one: the tries
        are not what is missing, so the loop spends the rest of the budget re-asking, and the
        story is finally filed as exhausted rather than as blocked on the one thing it is
        actually blocked on.

        The reason goes into `loop.qa.notes` because that is where `block_notes` — and so the
        gate body, and so the operator's `context.md` — reads it from. Prefixed with the turn
        that refused, since by the time a person reads it the only other clue is a counter.
        """
        reason = getattr(result, "notes", "") or "no reason given"
        self.logger.info("%s reported it cannot proceed; escalating: %s", what, reason)
        loop = loop.update(
            qa=loop.qa.model_copy(update={"notes": f"{what} reported it cannot proceed: {reason}"})
        )
        return self._gate(result, loop)

    def _gate(self, result: object, loop: QaLoop) -> Continue | Await:
        """`gate_qa`: hand the block to the auto-operator, or halt for a human.

        The counter is bumped here rather than in `resolve_operator`, because this is the
        one place both arms pass through — a `human`-mode gate is an escalation too, and
        numbering only the auto ones would make the second block of a `human` run read as
        the first. It doubles as the resolver's budget: past `MAX_QA_BLOCKS` this gate stops
        spending a resolver turn at all and every further block goes to a person. See that
        constant for why an *answering* resolver makes the difference load-bearing.
        """
        loop = loop.update(escalations=loop.escalations + 1)
        if self.operator_mode in {"human", "operator"} or loop.escalations > self.MAX_QA_BLOCKS:
            gate = self._escalation(loop)
            return Await(self._context, gate.body, self.read_operator, loop=loop)
        return Continue(result, self.resolve_operator, loop=loop)

    def _escalation(
        self,
        loop: QaLoop,
        result: OperatorResolution | None = None,
        findings: Sequence[Finding] = (),
    ) -> OperatorGate:
        """The gate body for this block — see `coder.shared.escalation`.

        `findings` is what the blocking gate saw, and it is passed here only for the ones
        `_route_findings` could not send anywhere: a finding with an owner has already gone
        to that owner, so anything reaching the operator is evidence nobody could act on.
        """
        return escalation(
            self,
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

    def _note_lane_budget(self, loop: QaLoop) -> None:
        """Log a QA lane over its advisory wall-clock budget. Never decides anything.

        Called from the guards that used to *end* on this comparison. What replaced the
        branch is this line, and the line is the point: the number stays visible to an
        operator reading the log or the telemetry, while the decision to stop belongs to the
        lap ceilings, which know whether the loop is converging. See `qa_lane_budget_s`.
        """
        if loop.lane_seconds >= self.qa_lane_budget_s:
            self.logger.info(
                "the QA lane has spent %.0fs of its %ds advisory budget — continuing, the "
                "lap ceilings decide when this story stops",
                loop.lane_seconds,
                self.qa_lane_budget_s,
                extra={"activity": True},
            )

    def _note_plan_budget(self, loop: QaLoop) -> None:
        """The same, for the plan lane. See `_note_lane_budget` and `plan_lane_budget_s`."""
        if loop.plan_lane_seconds >= self.plan_lane_budget_s:
            self.logger.info(
                "the QA plan lane has spent %.0fs of its %ds advisory budget — continuing, "
                "the plan-lap ceilings decide when this plan stops",
                loop.plan_lane_seconds,
                self.plan_lane_budget_s,
                extra={"activity": True},
            )

    def _exhausted(self, loop: QaLoop, spent: str = "") -> Continue | Await:
        """Out of budget — hand the block to the operator gate. There is no other exit.

        Every deciding site in this flow funnels through here, which is what makes it the
        right place for the ask. Running out of a repair budget is not a verdict on the
        story — it is a question the flow cannot answer by itself, and the gate is the only
        way to ask it. There is deliberately no cap on how many times a story can come back
        through here: a run-side backstop on asking is what turns "ask again" into "give up"
        (see `coder.shared.escalation`), and budgets keep counting down across a resume
        rather than resetting, so a second exhaustion still escalates rather than looping.

        `spent` is logged, not stored — `_escalation`'s `where` already reports every
        counter, so the phrase only needs to reach the log a human tailing the run reads.
        """
        if spent:
            self.logger.info("QA budget exhausted (%s) — escalating", spent)
        return self._gate(loop, loop)

    def _apply_fixes(
        self, *, qa_notes: str, operator_feedback: str | None, power: str, session: str
    ) -> QaResult:
        """`apply-qa-fixes.md`, which three nodes ran with three different argument sets.

        `operator_feedback` is omitted rather than passed empty on the plain fix path,
        because that node's YAML args did not include the key at all.

        `session` names the chain the turn resumes, and the caller decides which: the fix
        laps and the operator-guided lap run on the story's own backbone chain
        (`_story_chain()`) on purpose, both to stay one conversation with each other — the
        second is the same fixer being told its first attempt did not land, and it is worth
        far more knowing what it already tried than re-deriving it — and, when a session id
        was threaded in from a prior stage, to resume *that* implement session rather than
        opening a cold one. Applying a product note is not that worklist: it stays on its
        own `qa-feedback:` chain so a passing story's feedback turn never inherits a fix
        loop's failure context, or vice versa.
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
            session=session,
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
