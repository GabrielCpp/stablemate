"""Plan QA for a story, run it, and refuse to believe it passed — the port of
`coder/workflow.yaml`'s `flows.qa` (91 nodes, lines 2440-3593).

Reached from the main graph as the `qa_phase` flow node, and standalone as
`workhorse run coder qa`. It is the densest graph in the four workflows, and it is one
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
  field — see `schemas/qa.py`. No other agent turn in the four workflows has this shape.
* **an empty `story_path` ends the flow `exhausted`, it does not fail it.** `docs` raises on
  the same condition; `qa`'s `decide_qa_story` routed to `mark_qa_exhausted`, and the parent
  graph's `decide_qa_outcome` has an arm for it. Preserved as the YAML had it.
* the five budgets are `ClassVar` ints. None of the five is declared in `flows.qa.vars` — the
  guards carry branch literals (`"3"`, `"3"`, `"3"`, `"2"`, `"3"`) and the comments cite
  `vars.max_*` names that do not exist. Same inert-var finding as `dev`'s
  `max_validate_reworks`; recorded in the progress ledger.
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
* the three `mark-*` scripts (`mark-qa-assessment-failed.py`, `mark-qa-audit-failed.py`,
  `mark-regression-unresolved.py`) each printed one `qa_result`. They are the assignment at
  the deciding site, with the same default strings.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse_workflows.coder import paths
from workhorse_workflows.coder.nodes.backlog import file_backlog_items
from workhorse_workflows.coder.nodes.dev import read_operator_context, resolve_impl_context
from workhorse_workflows.coder.nodes.docs import detect_okf_docs
from workhorse_workflows.coder.nodes.evidence import verify_qa_evidence
from workhorse_workflows.coder.nodes.hygiene import check_sentinel_ids, flush_root_screenshots
from workhorse_workflows.coder.nodes.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.nodes.qa import (
    clear_qa_evidence,
    ensure_stack,
    run_qa_plan,
    validate_qa_plan,
)
from workhorse_workflows.coder.nodes.regression import (
    detect_regression_platform,
    run_regression_suite,
)
from workhorse_workflows.coder.nodes.review import check_feedback
from workhorse_workflows.coder.nodes.story import prepare_story, stamp_specs
from workhorse_workflows.coder.schemas.dev import OperatorResolution
from workhorse_workflows.coder.schemas.qa import (
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
from workhorse_workflows.coder.schemas.story import StoryPaths

UNBOUNDED = float("inf")


class Qa(Workflow):
    """Run a story's QA plan, gate the evidence, audit the pass, and bound every retry."""

    #: The story slug. ostler resolves the story path, spec dir and QA dir from it.
    story: str = ""
    #: The docs repo root. Empty resolves through `CODER_DOCS_PATH` / `AGENT_REPO_DIR`.
    docs_path: str = ""
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

    #: The five bounded retry budgets. All `ClassVar`, because none of the five is a var the
    #: YAML declared — each guard carries a branch literal. See the module docstring.
    MAX_QA_REWORKS: ClassVar[int] = 3
    MAX_CONTEXT_REWORKS: ClassVar[int] = 3
    MAX_PLAN_REWORKS: ClassVar[int] = 3
    MAX_SETUP_REWORKS: ClassVar[int] = 2
    MAX_REGRESSION_FIXES: ClassVar[int] = 3
    MAX_TRIAGE_SCOPES: ClassVar[int] = 2

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its `qa/` directory."""
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

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
            okf, self.build_context, loop=QaLoop(triage_scope=self.triage_scope_count)
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
        )
        result = self.call(
            validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path
        )
        loop = loop.update(context_status=result.status, context_notes=result.notes)
        if result.status == "passed":
            return Continue(result, self.plan, loop=loop)
        if loop.context_rework >= self.MAX_CONTEXT_REWORKS:
            return self._exhausted(loop)
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
        loop = loop.with_qa(reply.qa_result)
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
                "run_assessment_notes": loop.assessment_notes,
                "audit_notes": loop.audit_notes,
                "evidence_notes": loop.qa.notes,
            },
        )
        loop = loop.cleared()
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        validation = self.call(validate_qa_plan, self.ctx.spec_dir, self.docs_path)
        loop = loop.update(plan_validation_notes=validation.notes)
        if validation.status == "passed":
            return Continue(validation, self.review_plan, loop=loop)
        return self._guard_plan(validation, loop)

    def review_plan(self, loop: QaLoop) -> Continue | Await | Done:
        """An independent read of a plan that already parses — does it test the story?

        `review_qa_plan` + `decide_qa_plan_review`. `revise`, and a blank taking the YAML's
        `default:`, spends a plan rework; only `approved` reaches the stack.
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
        loop = loop.update(plan_review_notes=review.notes)
        if review.disposition == "approved":
            return Continue(review, self.stack, loop=loop)
        return self._guard_plan(review, loop)

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
            return self._guard_setup(status, loop)
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
        loop = loop.update(assessment_notes=assessment.notes)

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
        loop = loop.update(audit_notes=result.notes)
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
            QaFlowResult(qa=loop.qa, qa_rework=loop.qa_rework, triage_scope=loop.triage_scope)
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
        return Continue(result, self.build_context, loop=loop.with_qa(result))

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
                regression_fix=loop.regression_fix + 1, regression_fix_applied=True
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
            loop=loop.update(qa=result, qa_rework=loop.qa_rework + 1),
        )

    # ── the setup-repair loop ─────────────────────────────────────────────────────────

    def setup_fix(self, loop: QaLoop) -> Continue | Await | Done:
        """Repair the stack manifest that would not come up, then try it again.

        `setup_fix` + `incr_setup` + `decide_setup`. `unfixable` — the YAML's default for a
        fixer that produced nothing — escalates to the operator rather than looping.

        `stack_manifest` is passed rather than assumed: this node's whole job is repairing it,
        and a fixer that authors `qa-stack.yml` at the root while the run reads
        `<service>/qa-stack.yml` loops forever on `skip`.
        """
        self.logger.info("repairing the QA stack", extra={"activity": True})
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
            },
        )
        loop = loop.update(setup_rework=loop.setup_rework + 1)
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
        return Await(self._context, loop.block_notes, self.read_operator, loop=loop)

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
                )
            )
        return Continue(answer, self.apply_resolved, loop=loop, content=answer.content)

    def apply_resolved(self, loop: QaLoop, content: str) -> Continue:
        """Apply the operator's answer as a QA fix, and spend a rework on it.

        `apply_qa_resolved` + `incr_qa`. The same prompt `apply_qa_fixes` runs, at medium
        rather than high, because the hard thinking was the operator's.
        """
        result = self._apply_fixes(
            qa_notes=loop.qa.notes, operator_feedback=content, power="medium"
        )
        return Continue(
            result,
            self.build_context,
            loop=loop.update(qa=result, qa_rework=loop.qa_rework + 1),
        )

    # ── routers and shared turns, none of them states ─────────────────────────────────

    def _guard_plan(self, result: object, loop: QaLoop) -> Continue | Done:
        """`guard_qa_plan` + `incr_qa_plan`: re-plan, or give up on the story."""
        if loop.plan_rework >= self.MAX_PLAN_REWORKS:
            return self._exhausted(loop)
        return Continue(result, self.plan, loop=loop.update(plan_rework=loop.plan_rework + 1))

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
            return self._exhausted(loop)
        self.logger.info("granting the one verification-only bonus pass")
        return Continue(result, self.apply_fixes, loop=loop.update(bonus_used=True))

    def _fixable(self, result: object, loop: QaLoop) -> Continue | Done:
        """`decide_qa_fixable`: in a `dev` run the findings are reported, not fixed."""
        if self.target_env == "dev":
            return Continue(result, self.report_dev, loop=loop)
        return self._guard_qa(result, loop)

    def _gate(self, result: object, loop: QaLoop) -> Continue | Await:
        """`gate_qa`: hand the block to the auto-operator, or halt for a human."""
        if self.operator_mode == "human":
            return Await(self._context, loop.block_notes, self.read_operator, loop=loop)
        return Continue(result, self.resolve_operator, loop=loop)

    def _exhausted(self, loop: QaLoop) -> Done:
        """`mark_qa_exhausted`: the budget is spent, and the parent decides what that costs."""
        return Done(
            QaFlowResult(
                qa=loop.qa, qa_rework=loop.qa_rework, triage_scope=loop.triage_scope
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
