"""Review a story's implementation and drive the findings to settled.

Reached from the main graph as a flow that reads nothing back, and standalone as
`workhorse-coder run review` for a PR that no story pipeline produced::

    start (code review) → review ⇄ apply (bounded) → feedback poll → done
                               ↘ operator gate ↗

The code review and the reuse hunt are one turn, `start`'s single review pass: the reuse
hunt is a lens on the diff rather than a second turn re-reading it cold.

**Three call sites share one `apply-review.md` node** — the review loop, the operator
resolution, and the feedback pass. The driver ids an agent turn by its prompt stem, so the
three are one node id; nothing reads that output by node name, and what distinguishes the
sites is their arguments and where they go next.

**The lane is split in two along one line: who judges, and who changes the code.** The
judging turns — code review, reuse, the implementation verdict — are cold by design; a
reviewer that inherited the author's context is reviewing its own reasoning. The three
apply turns are the opposite case: they resume the *implementer's* conversation — the
story's backbone chain, which the dev lane left open in this run's directory — because a
finding is a request to change code somebody just wrote and the turn that wrote it already
knows why the line is there. Nothing is threaded in to make that happen: the key is derived
from the story slug, and a lane with no dev lane in front of it simply finds no chain and
runs cold. That also makes the cheap power tier sufficient for an apply, which is where this
lane's cost was. `MAX_SESSION_TURNS` bounds the conversation across both lanes — the count
arrives as `inherited_turns` from `DevResult.session_turns`, seeds `ReviewLoop.session_turns`
in `start`, and keeps going here.

Two shapes worth naming before reading the states:

* **The operator gate never decides on the operator's behalf**, exactly as `author`,
  `surveyor` and `dev` settle it. `resolve_review` below investigates and always `Await`s —
  it does not read a `decision` field to choose between looping and waiting, because there is
  no loop it could choose instead: a block always parks. `_gate` decides only whether the
  resolver gets a turn first (`ReviewLoop.blocks` below `MAX_REVIEW_BLOCKS`) or the block goes
  straight to a human — never whether to wait at all.
* **The review verdict is threaded, not read back.** `review_implementation` reads the
  findings produced inside `start`, one state earlier. `self.output` reads only *node*
  outputs, and an agent turn is not a node, so the model travels as a state parameter. It is
  the one genuinely large thing this flow checkpoints, and it is checkpointed because the
  state that consumes it is also the state the feedback loop returns to. The operator arm
  does not carry it: every path out of that arm goes back to `start`, which reviews the new
  code from scratch, so a copy threaded through the gate would be a stale one nobody reads.
  Node outputs — the operator's answer, a polled feedback note — are read back with
  `self.output` rather than threaded at all.

The three counters travel as one `ReviewLoop`: `rework` goes back to zero on the transition
to `start`, `blocks` is the cumulative outer budget that survives it so repeated operator
cycles terminate, and `session_turns` is the shared conversation bound. Both ceilings are
`ClassVar` ints rather than inputs.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.conversation import spend_turn, story_chain
from workhorse_workflows.coder.shared.dev import (
    plan_summary,
    read_operator_context,
)
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.review import (
    check_feedback,
    clear_review_resolution,
    resolve_review_context,
    verify_review_resolution,
)
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    stamp_specs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    ImplResult,
    OperatorGate,
    OperatorResolution,
)
from workhorse_workflows.coder.shared.schemas.review import (
    CodeReviewResult,
    ReviewFinding,
    ReviewLoop,
    ReviewResult,
    ReviewVerdict,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels

#: `timeout: infinity` — the resolver stands in for a human and must not be cut off
#: mid-resolution. A finite number of seconds here caps it.
UNBOUNDED = float("inf")

#: How many turns the story's conversation carries before it is recycled — the same number
#: and the same reasoning as `dev`'s. A constant rather than a field: nobody sets it, and a
#: `--param` nobody passes is an input in name only.
MAX_SESSION_TURNS = 8

#: The confidence at or above which a code-review finding binds. The reviewer scores every
#: finding it raises and reports all of them; this line decides which ones the implementation
#: reviewer must fold into its verdict and which travel as context. It is Python's call
#: rather than the prompt's because "drop the ones you scored below 80" is a filter nothing
#: downstream can check — a turn that silently kept one, or silently dropped one it scored 85,
#: reads identically. Here the whole list is parsed and the split is a comparison.
MUST_FIX_CONFIDENCE = 80


def split_on_confidence(
    findings: Sequence[ReviewFinding],
) -> tuple[list[ReviewFinding], list[ReviewFinding]]:
    """Split code-review findings into the mandatory ones and the advisory ones."""
    must_fix = [f for f in findings if f.score >= MUST_FIX_CONFIDENCE]
    advisory = [f for f in findings if f.score < MUST_FIX_CONFIDENCE]
    return must_fix, advisory


def findings_block(findings: Sequence[ReviewFinding]) -> str:
    """Render findings as the markdown the review prompt inlines, or `None.` for an empty set.

    Rendered here rather than looped in the template so the prompt carries no `{% if %}` arm
    for the empty case: both blocks are always present and always say something.
    """
    if not findings:
        return "None."
    return "\n".join(
        f"- **{f.target}** — {f.issue}\n"
        f"  - Category: {f.category} (confidence {f.score})\n"
        f"  - Required fix: {f.repair}"
        for f in findings
    )


def require_story_file(ctx: StoryPaths) -> None:
    """Fail the run when the slug did not resolve to a story file that exists.

    Every review turn is dispatched with this path and edits nothing else, so a blank or
    absent one is a bad input rather than something an agent can work around. Checked here,
    once, instead of asked of each prompt: a turn told to "return blocked if the path is
    blank" is being asked to report a fact the flow already holds, and reports it three
    laps and one operator gate later than this does.
    """
    if not ctx.story_path or not Path(ctx.story_path).is_file():
        raise WorkflowFailed(
            f"story '{ctx.story_slug}' did not resolve to a story file "
            f"({ctx.story_path or 'no path'}); nothing to review."
        )


class Review(Workflow):
    """Review one story's implementation, and settle every finding it raises."""

    #: The story slug. ostler resolves the story path and spec dir from it.
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
    #: An explicit repo name for a standalone PR review. Empty derives the affected set
    #: from the plan context the dev flow wrote.
    repo: str = ""
    #: The branch under review. Empty lets the reviewer take the repo's current one.
    branch: str = ""
    #: The PR to comment on. Empty lets the reviewer derive one from the branch, and no
    #: open PR at all is fine — the review runs against local changes either way.
    pr_number: str = ""
    #: How many turns the story's conversation had already spent before this flow entered
    #: it. Carried from `DevResult.session_turns` so the recycle threshold bounds the whole
    #: conversation rather than each lane's share of it. A run-frozen input: `start` seeds
    #: `ReviewLoop.session_turns` from it, and every lap after that counts onto the loop.
    inherited_turns: int = 0


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Apply passes before the loop escalates to the operator. A `ClassVar` rather than an
    #: input: it is not an operator control — see the module docstring.
    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    #: Trips through the operator gate that get a resolver turn before every further block
    #: goes straight to a human — not a cap on how many times review may block; there isn't
    #: one. This budget survives the local rework reset after an operator answer.
    MAX_REVIEW_BLOCKS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths, the workspace to directories, and the repos to review.

        None of the three is branched on and every state below reads the same values, which
        is the rule for `setup`. `resolve_review_context` belongs here rather than in `start`
        because the docs repo it resolves is the *cwd* of the three review turns, and a cwd
        that changed between them would mean they were not reviewing the same thing.

        Nothing seeds the implementer chain: its key comes from the story slug, so a dev
        lane earlier in the same run has already left the conversation under it, and a
        standalone PR review finds nothing there and runs cold.
        """
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        require_story_file(ctx)
        self.call(resolve_review_context, ctx.spec_dir, self.repo, self.docs_path)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which review round the next state is on.

        Every transition but the first carries a `ReviewLoop`, so all three budgets are in
        hand here and no state has to stash a copy of them. `setup` and the first entry to
        `start` run before any loop exists, and simply report nothing.
        """
        loop = params.get("loop")
        if not isinstance(loop, ReviewLoop):
            return self.labels()
        return self.labels() | counter_labels(
            loop.model_dump(), "review", ReviewLoop.COUNT_LABELS
        )

    # --- the feeder review ---------------------------------------------------

    def start(self, loop: ReviewLoop | None = None) -> Continue | Await:
        """Review the diff — bugs, the coding standard, and reuse — in one pass.

        A PR is not required: uncommitted working-tree edits and story-branch commits are
        both reviewable, and if a PR happens to be open the findings are posted as inline
        comments too. The findings ride forward in the result so the implementation reviewer
        sees them without re-deriving them.

        Duplication and missed reuse are a lens of this pass rather than a turn of their own.
        They were a second turn once; over the same diff and the same story it cost a full
        cold ramp-up to ask a question the reviewer already has the diff open for, and the
        findings arrive tagged with a `category` so the binding reviewer can still tell them
        apart.

        The feeder chain is reset before the pass runs, not after: this is also where the
        operator loop comes back to, and `apply_resolved`'s docstring is explicit that a
        re-entry here is a fresh review round, not a continuation of the one that got
        blocked — so each entry looks at the code with no memory of the last round's
        findings, whether that is the first entry or the fifth.

        No loop is the first entry, and it is where the three budgets are seeded: the two
        rework counters at zero, and the conversation's turn count at whatever the dev lane
        already spent. The operator arm re-enters carrying one, and keeps it.
        """
        lap = loop or ReviewLoop(session_turns=self.inherited_turns)
        self.logger.info("reviewing %s", self.ctx.story_slug, extra={"activity": True})
        # Before the findings that the round's settlement will be checked against exist. Here
        # rather than in `setup` because the operator loop re-enters this state without it,
        # and that re-entry is a fresh review round like any other.
        self.call(clear_review_resolution, self.ctx.spec_dir, self.ctx.story_slug)
        self.reset_session(self._feeder_chain)
        turn = roles.turn(self, "code-review", returns=CodeReviewResult)
        code_review = self.agent(
            turn.prompt,
            returns=turn.returns,
            # medium: reads a diff and judges it against the standard the implementer
            # was given. Real judgement, but bounded by the diff in front of it.
            power="medium",
            session=self._feeder_chain,
            cwd=self._docs_repo,
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_path": self.ctx.story_path,
                "affected_repo_paths": self._repos,
                "branch": self.branch,
                "pr_number": self.pr_number,
            },
        )
        if code_review.blocked:
            # `blocked` here is not "no findings" — it is a pass that could not read the
            # diff at all: the repos it was given are not the ones the change landed in, or
            # the tree is in a state no review of it would mean anything in. Running the
            # binding reviewer over that anyway produces a verdict on nothing, and logging
            # the warning was the run's only record that it had. It goes to the operator
            # like every other block, and their answer re-enters here for a fresh pass.
            return self._gate(
                code_review,
                code_review.findings_summary or "the code-review pass could not read the diff",
                lap,
                where="the code-review pass",
            )
        return Continue(code_review, self.review, code_review=code_review, loop=lap)

    # --- the review loop ----------------------------------------------------

    def review(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Review the implementation against the story, and route on the verdict.

        `review_implementation` + `stamp_specs_review` + `decide_impl`. Only `approved` exits
        the loop, `blocked` goes to the operator, and `needs_changes` takes the rework guard.
        There is no fourth arm: the verdict is a required `Literal`, so a reviewer that did
        not speak is a parse failure the runner retries rather than a blank this state has to
        read an intent into.

        The stamp runs on every pass, including the one the feedback loop returns for: the
        review turn can rewrite spec docs, and the frontmatter that
        makes them OKF Concepts is only as reliable as the model's memory, so it is applied
        mechanically each time rather than trusted once.

        The code-review findings arrive already split at `MUST_FIX_CONFIDENCE`: the reviewer
        below is handed a mandatory list and an advisory one instead of a struct it was
        trusted to filter.
        """
        must_fix, advisory = split_on_confidence(code_review.findings)
        turn = roles.turn(self, "review-implementation", returns=ReviewVerdict)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            # high: the binding judgement on whether the story was actually implemented.
            power="high",
            cwd=self._docs_repo,
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
                "must_fix_findings": findings_block(must_fix),
                "advisory_findings": findings_block(advisory),
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "approved":
            return Continue(result, self.poll_feedback, code_review=code_review, loop=loop)
        if result.blocked:
            # A reviewer that could not reach a verdict is not a reviewer demanding changes:
            # the apply turn would be handed nothing to act on, and each futile lap ends
            # back here with the same reason. Straight to the gate, rework budget unspent.
            return self._gate(result, result.notes, loop)
        return self._guard(result, result.notes, code_review, loop)

    def apply(
        self, notes: str, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Resolve the findings, then let ostler decide whether they are actually resolved.

        `apply_review` + `verify_review_resolution` + `decide_apply_review`. The gate is the
        anti-gaming half and it can only downgrade: the turn's self-reported status is
        overwritten by what `ostler edit settle-review` verified per finding against the
        cited artifacts.

        `applied` exits the loop **without a full re-review**, deliberately — re-running the
        reviewer here is what let it re-litigate settled findings and move the goalposts, and
        the deterministic settle is the re-verify. `blocked` escalates that one finding to
        the operator. Anything else spends a rework and re-applies only what is still open.

        The turn's own reply is dropped rather than bound: what it wrote that matters is the
        verdict file, and the gate reads that.
        """
        spent = self._spend_turn(loop)
        turn = roles.turn(self, "apply-review", returns=ImplResult)
        self.agent(
            turn.prompt,
            returns=turn.returns,
            power=self._apply_power(),
            add_dirs=workspace_dirs(self),
            session=self._impl_chain(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": notes,
            },
        )
        # The branch below reads the *settled* status, never the turn's own claim, which is
        # why the claim is not even bound: a turn that wrote no verdict has produced nothing
        # to settle.
        settled = self.call(
            verify_review_resolution, self.ctx.spec_dir, self.docs_path, self.ctx.story_slug
        )
        if settled.status == "applied":
            return Continue(settled, self.poll_feedback, code_review=code_review, loop=spent)
        if settled.blocked:
            return self._gate(settled, notes, spent, where="applying the review findings")
        return self._guard(
            settled,
            notes,
            code_review,
            spent.model_copy(update={"rework": spent.rework + 1}),
        )

    def _guard(
        self, result: object, notes: str, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """`guard_review`: another apply pass, or the operator.

        Not a state — the routing half of a branch, called from the two states that can
        decide the review stage is stuck. `_`-prefixed so state discovery does not pick it up.
        """
        if loop.rework >= self.MAX_REVIEW_REWORKS:
            return self._gate(result, notes, loop)
        return Continue(result, self.apply, notes=notes, code_review=code_review, loop=loop)

    def _gate(
        self,
        result: object,
        notes: str,
        loop: ReviewLoop,
        where: str = "the implementation-review stage",
    ) -> Continue | Await:
        """`gate_review`: hand the block to the resolver, or straight to a human.

        Reached when the loop exhausts its budget or the settlement reports a finding
        unresolvable. Both are real: an unsatisfiable finding may need a product decision
        that no amount of re-applying will produce. There is no dead end here — a block
        always reaches a human eventually, either through the resolver or directly once
        `loop.blocks` is spent — never a terminal failure.

        The code review does not travel down this arm. Every path out of it ends at `start`,
        which runs a fresh one against whatever the operator's answer changed; carrying the
        old findings through four more states would only hand them to a turn that replaces
        them.
        """
        if self.operator_mode in {"human", "operator"} or loop.blocks >= self.MAX_REVIEW_BLOCKS:
            gate = self._escalation(notes, loop.blocks, where=where)
            return Await(
                context_path(self), gate.body, self.read_operator, notes=notes, loop=loop
            )
        return Continue(result, self.resolve_review, notes=notes, loop=loop, where=where)

    # --- the operator arm ---------------------------------------------------

    def resolve_review(
        self,
        notes: str,
        loop: ReviewLoop,
        where: str = "the implementation-review stage",
    ) -> Continue | Await:
        """Resolve a review block from what is already written down, or park for the operator.

        `resolve_review` + the `await_operator_review` that followed it unconditionally; see
        the module docstring. A review block is the one most often already decided: an
        unsatisfiable finding is frequently a "which convention holds here" question, and
        the convention is in an installed skill. When the resolver can quote it, it writes
        the answer into `context.md` and the flow continues to `read_operator`, which reads
        that file whoever wrote it. When it cannot, this parks, as it always did.
        """
        self.logger.info("resolving the review block", extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: standing in for a human, with full tool access, on a
            # finding nobody else could settle.
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=workspace_dirs(self),
            args=resolver_args(
                self, block_kind="review", notes=notes, docs_path=self.docs_path
            ),
        )
        spent = loop.model_copy(update={"blocks": loop.blocks + 1})
        if answered(self, result, "review"):
            return Continue(result, self.read_operator, notes=notes, loop=spent)
        # See `dev.flow.resolve_plan`: the escalating resolver's note is already in this
        # file and `Await` writes over it, so the body handed here carries that note
        # forward along with what the resolver tried.
        return Await(
            context_path(self),
            self._escalation(notes, loop.blocks, result, where=where).body,
            self.read_operator,
            notes=notes,
            loop=spent,
        )

    def read_operator(self, notes: str, loop: ReviewLoop) -> Continue:
        """Consume the answer and apply it as the work.

        The consume half of `await_operator.py`. Unlike `dev`'s copy there is no scope
        branch: `await_operator_review` went to `apply_review_resolved` unconditionally, so
        an epic-scoped answer to a review block is applied as a story-level fix. Preserved
        rather than harmonised, and recorded as a finding — the two gates genuinely differ.

        The answer itself is not threaded on: it is a node output, and `apply_resolved` reads
        it back off this node rather than being handed a second copy to checkpoint.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        return Continue(answer, self.apply_resolved, notes=notes, loop=loop)

    def apply_resolved(self, notes: str, loop: ReviewLoop) -> Continue | Await:
        """Apply the operator's resolution, then start the review over with a fresh budget.

        Going back to `start` re-runs both feeder reviews against the new code, which is
        what makes the answer binding rather than asserted: the same reviewer has to look
        again. The rework counter goes back to zero on that transition; the block budget does
        not, which is what makes repeated operator cycles terminate.

        A turn that reports it could not apply the answer goes back to the operator instead
        of re-entering the loop: re-reviewing unchanged code produces the same findings and
        the same block, one full review round later. The operator is told it was their own
        answer that could not be applied, which is a different question from the original.
        """
        spent = self._spend_turn(loop)
        turn = roles.turn(self, "apply-review", returns=ImplResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power=self._apply_power(),
            add_dirs=workspace_dirs(self),
            session=self._impl_chain(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": notes,
                "operator_feedback": self.output(read_operator_context).content,
            },
        )
        if result.blocked:
            return self._gate(
                result,
                result.notes or notes,
                spent,
                where="applying the operator's own resolution",
            )
        return Continue(result, self.start, loop=spent.model_copy(update={"rework": 0}))

    # --- the non-blocking feedback checkpoint -------------------------------

    def poll_feedback(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Done:
        """Did a human drop a note into the run's inbox while the run was busy?

        `check_impl_feedback` + `decide_impl_feedback`. Never halts and never asks: polling
        the inbox replies to the oldest outstanding message, so one drop buys exactly one
        rework pass. No feedback — the common case — ends the flow and the caller proceeds
        to QA.

        The note is not threaded on: polling records it as this node's output, and
        `apply_feedback` reads it back from there rather than carrying a second copy.
        """
        feedback = self.call(check_feedback, str(self.run_dir))
        if not feedback.present:
            return Done(ReviewResult())
        self.logger.info("operator feedback found — one rework pass", extra={"activity": True})
        return Continue(feedback, self.apply_feedback, code_review=code_review, loop=loop)

    def apply_feedback(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Rework against the operator's notes, then re-review.

        No review findings go in: the feedback *is* the work, and handing the applier a stale
        set of already-settled findings would invite it to redo them. The rework counter is
        carried rather than reset: the feedback pass re-enters the review loop with whatever
        allowance is left.

        Feedback the turn reports it cannot act on is the one case in this flow where the
        block came from a human who is not waiting: they dropped a note and moved on. It
        still parks, because the alternative is re-reviewing code the feedback never
        reached and reporting the story approved over it.
        """
        content = self.output(check_feedback).content
        spent = self._spend_turn(loop)
        turn = roles.turn(self, "apply-review", returns=ImplResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power=self._apply_power(),
            add_dirs=workspace_dirs(self),
            session=self._impl_chain(),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": "",
                "operator_feedback": content,
            },
        )
        if result.blocked:
            return self._gate(
                result,
                result.notes or content,
                spent,
                where="applying the operator's feedback note",
            )
        return Continue(result, self.review, code_review=code_review, loop=spent)

    # --- shared -------------------------------------------------------------

    @property
    def _docs_repo(self) -> str:
        """The docs repo, and the cwd of the three review turns."""
        return self.output(resolve_review_context).docs_repo_path

    @property
    def _repos(self) -> list[str]:
        """The code repos this story touched, which are what the reviewers may read."""
        return list(self.output(resolve_review_context).affected_repo_paths)

    def _escalation(
        self,
        notes: str,
        blocks: int,
        result: OperatorResolution | None = None,
        where: str = "the implementation-review stage",
        findings: Sequence[Finding] = (),
    ) -> OperatorGate:
        """The gate body for a block in this lane — see `coder.shared.escalation`.

        `where` is a parameter because the holistic reviewer is no longer the only turn
        here that can report it cannot finish.
        """
        return escalation(
            self,
            block_kind="review",
            where=where,
            notes=notes,
            number=blocks,
            result=result,
            findings=findings,
        )

    @property
    def _feeder_chain(self) -> str:
        """The code-review pass's own conversation — review-local by design.

        Named for the review alone, never the story's backbone: a reviewer that inherited the
        author's context is reviewing its own reasoning, so the judging turns are the half
        of this lane that must stay cold. The key must also never collide with the
        implementer chain, since the two are reset on entirely different schedules — this
        one on every entry to `start`, not once per story.
        """
        return f"review-feeders:{self.ctx.story_slug}"

    def _apply_power(self) -> str:
        """How much reasoning an apply turn gets, given whose context it runs in.

        Resuming the implementer's conversation is what makes the cheap tier sufficient: the
        reasoning that needed the expensive one happened on the implement turn and is still
        in the context, and what is being asked for now is a named change to code the turn
        already understands. With no session to resume — a standalone PR review — the turn
        is cold and pays the old price.

        The chain itself is what is asked, rather than anything threaded in: it is right on a
        resumed run whose conversation exists but whose entry parameters are long gone, and
        it correctly reports cold once the recycler has reset the chain.
        """
        return "low" if self.chain_session(self._impl_chain()) else "high"

    def _impl_chain(self) -> str:
        """The implementer's conversation, which the *apply* turns rejoin.

        A finding is a request to change code somebody just wrote, and the cheapest turn
        that can act on it is the one that wrote it: it knows why the line is there, what it
        already tried, and which files it touched. The dev lane opened this chain under the
        same story-derived key earlier in the run; a standalone PR review with no dev lane in
        front of it finds no chain and the CLI mints one on first use, which is a cold turn
        exactly as before.
        """
        return story_chain(self.ctx.story_slug)

    def _spend_turn(self, loop: ReviewLoop) -> ReviewLoop:
        """Count one apply turn onto the implementer conversation, recycling it when full.

        The lap comes back with the new count on it, so the three apply states thread one
        value rather than reconciling a returned integer against the bundle they were given.
        """
        spent = spend_turn(
            self, self._impl_chain(), loop.session_turns, MAX_SESSION_TURNS
        )
        return loop.model_copy(update={"session_turns": spent})


__all__ = ["Review"]
