"""Review a story's implementation and drive the findings to settled — the port of
`coder/workflow.yaml`'s `flows.review` (18 nodes, lines 1842-2173).

Reached from the main graph as a `type: flow` node that reads nothing back, and standalone as
`workhorse-coder run review` for a PR that no story pipeline produced::

    code review → code reuse → review ⇄ apply (bounded) → feedback poll → done
                                    ↘ operator gate ↗

Eighteen nodes become nine states. Four are `type: branch` routers reading a value the node
above them had just produced; two are the `seed`/`incr` pair for the rework counter, which is
a state parameter here; and `stamp_specs_review` merges into the review state it always ran
directly after.

**Three call sites share one `apply-review.md` node**, as the YAML also had them — the review
loop, the operator resolution, and the feedback pass. The driver ids an agent turn by its
prompt stem, so the three are one node id where the YAML had three; nothing reads that output
by node name, and what distinguished the sites was their arguments and where they went next.

Divergences from the YAML, all deliberate:

* **The operator gate is split**, exactly as `author`, `surveyor` and `dev` settled it: the
  YAML's `resolve_review` fell into `await_operator_review` unconditionally and the *file's*
  `STATUS:` line decided whether that halted. `Await` waits unconditionally, so
  `resolve_review` below branches on the resolver's own `decision` and only the escalated arm
  waits. The consume half of `await_operator.py` is `read_operator_context`, a node.
* `review_rework_count` was a var with `seed`/`incr` nodes; it is the `review_rework`
  parameter. The re-seed that `apply_review_resolved → reset_review` performed is the
  transition back to `start` not carrying it. `review_blocks` is the cumulative outer
  budget that does survive that transition, so repeated operator cycles terminate.
* `guard_review`'s comment cites `vars.max_review_reworks`, which neither this flow nor any
  caller declares — the literal `"3"` on the branch is the only budget there is. It is
  `MAX_REVIEW_REWORKS` here, a `ClassVar` rather than an input, so the port does not invent
  an operator control the YAML did not have. Recorded in the progress ledger as a finding;
  it is the third instance of that shape, after `genesis`'s `max_genesis_reworks` and `dev`'s
  `max_validate_reworks`.
* **the two review verdicts are threaded, not read back.** `review_implementation` takes
  `code_review_result` and `code_reuse_result`, produced two and three states earlier; under
  the YAML engine they sat in the run context for the flow's lifetime. `self.output` reads
  only *node* outputs, and an agent turn is not a node, so the two models travel as state
  parameters. They are the one genuinely large thing this flow checkpoints, and they are
  checkpointed because the state that consumes them is also the state the feedback loop and
  the operator loop return to.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.escalation import compose_escalation
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
)
from workhorse_workflows.coder.shared.schemas.dev import (
    ImplResult,
    OperatorGate,
    OperatorResolution,
)
from workhorse_workflows.coder.shared.schemas.review import (
    CodeReuseResult,
    CodeReviewResult,
    ReviewResult,
    ReviewVerdict,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels

#: `timeout: infinity` — the resolver stands in for a human and must not be cut off
#: mid-resolution. A finite number of seconds here caps it.
UNBOUNDED = float("inf")


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


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Apply passes before the loop escalates to the operator. `ClassVar` because the YAML
    #: exposed no var for it — see the module docstring.
    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    #: Trips through the operator gate before review is declared a dead end. This outer
    #: budget survives the local rework reset after an operator answer.
    MAX_REVIEW_BLOCKS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths, the workspace to directories, and the repos to review.

        None of the three is branched on and every state below reads the same values, which
        is the rule for `setup`. `resolve_review_context` belongs here rather than in `start`
        because the docs repo it resolves is the *cwd* of the three review turns, and a cwd
        that changed between them would mean they were not reviewing the same thing.
        """
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        self.call(resolve_review_context, ctx.spec_dir, self.repo, self.docs_path)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    #: The local rework and cumulative operator-cycle budgets.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("review_rework", "review_blocks")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which review round the next state is on."""
        return self.labels() | counter_labels(params, "review", self.BUDGET_LABELS)

    # --- the two feeder reviews ---------------------------------------------

    def start(self, review_blocks: int = 0) -> Continue:
        """Run the native code-review skill over each affected repo's local changes.

        A PR is not required: uncommitted working-tree edits and story-branch commits are
        both reviewable, and if a PR happens to be open the findings are posted as inline
        comments too. The findings ride forward in the result so the implementation reviewer
        sees them without re-deriving them.

        This is also where the operator loop comes back to, which re-seeds the local rework
        budget while preserving `review_blocks`: an operator who actually answered gets a
        clean allowance and a fresh read of the code, but not an unbounded number of cycles.
        """
        self.logger.info("reviewing %s", self.ctx.story_slug, extra={"activity": True})
        # Before the findings that the round's settlement will be checked against exist. Here
        # rather than in `setup` because the operator loop re-enters this state without it,
        # and that re-entry is a fresh review round like any other.
        self.call(clear_review_resolution, self.docs_path, self.ctx.story_slug)
        result = self.agent(
            "prompts/code-review.md",
            returns=CodeReviewResult,
            # medium: runs a packaged review skill over a diff. The judgement it needs is
            # the skill's, not the caller's.
            power="medium",
            cwd=self._docs_repo,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "affected_repo_paths": self._repos,
                "branch": self.branch,
                "pr_number": self.pr_number,
            },
        )
        return Continue(result, self.reuse, code_review=result, review_blocks=review_blocks)

    def reuse(self, code_review: CodeReviewResult, review_blocks: int = 0) -> Continue:
        """Hunt the reuse problems the diff introduced: duplication, and hand-rolled helpers.

        A dedicated pass rather than one of five things the implementation reviewer juggles.
        Its findings fold into that reviewer's verdict, so a Major reuse finding drives the
        same bounded rework loop as any other — filed as work, not silently as backlog.
        """
        result = self.agent(
            "prompts/code-reuse.md",
            returns=CodeReuseResult,
            # high: semantic "is this already implemented elsewhere?" matching across the
            # codebase — the same discovery task as dev's check_code_reuse.
            power="high",
            cwd=self._docs_repo,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "affected_repo_paths": self._repos,
            },
        )
        return Continue(
            result,
            self.review,
            code_review=code_review,
            code_reuse=result,
            review_blocks=review_blocks,
        )

    # --- the review loop ----------------------------------------------------

    def review(
        self,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_rework: int = 0,
        review_blocks: int = 0,
    ) -> Continue | Await:
        """Review the implementation against the story, and route on the verdict.

        `review_implementation` + `stamp_specs_review` + `decide_impl`. Only `approved` exits
        the loop; `needs_changes` and a blank alike take the YAML's `default:` arm, which is
        the rework guard — a reviewer that did not speak has not approved anything.

        The stamp runs on every pass, including the one the feedback loop returns for, which
        is the YAML's wiring: the review turn can rewrite spec docs and the frontmatter that
        makes them OKF Concepts is only as reliable as the model's memory, so it is applied
        mechanically each time rather than trusted once.
        """
        result = self.agent(
            "prompts/review-implementation.md",
            returns=ReviewVerdict,
            # high: the binding judgement on whether the story was actually implemented.
            power="high",
            cwd=self._docs_repo,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "code_review_result": code_review,
                "code_reuse_result": code_reuse,
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "approved":
            return Continue(
                result,
                self.poll_feedback,
                code_review=code_review,
                code_reuse=code_reuse,
                review_rework=review_rework,
                review_blocks=review_blocks,
            )
        return self._guard(
            result,
            result.notes,
            code_review,
            code_reuse,
            review_rework,
            review_blocks,
        )

    def apply(
        self,
        notes: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_rework: int,
        review_blocks: int = 0,
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
        """
        claim = self.agent(
            "prompts/apply-review.md",
            returns=ImplResult,
            # high: writes the production change the reviewer demanded, across whatever the
            # findings touch.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": notes,
            },
        )
        # The branch below reads the *settled* status, never the turn's own claim: the YAML
        # overwrote `impl_result` with the verifier's output for exactly this reason.
        settled = self.call(
            verify_review_resolution,
            self.docs_path,
            self.ctx.story_slug,
            claim.status,
            claim.notes,
        )
        if settled.status == "applied":
            return Continue(
                settled,
                self.poll_feedback,
                code_review=code_review,
                code_reuse=code_reuse,
                review_rework=review_rework,
                review_blocks=review_blocks,
            )
        if settled.status == "blocked":
            return self._gate(settled, notes, code_review, code_reuse, review_blocks)
        return self._guard(
            settled,
            notes,
            code_review,
            code_reuse,
            review_rework + 1,
            review_blocks,
        )

    def _guard(
        self,
        result: object,
        notes: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_rework: int,
        review_blocks: int,
    ) -> Continue | Await:
        """`guard_review`: another apply pass, or the operator.

        Not a state — the routing half of a branch, called from the two states that can
        decide the review stage is stuck. `_`-prefixed so state discovery does not pick it up.
        """
        if review_rework >= self.MAX_REVIEW_REWORKS:
            return self._gate(result, notes, code_review, code_reuse, review_blocks)
        return Continue(
            result,
            self.apply,
            notes=notes,
            code_review=code_review,
            code_reuse=code_reuse,
            review_rework=review_rework,
            review_blocks=review_blocks,
        )

    def _gate(
        self,
        result: object,
        notes: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_blocks: int,
    ) -> Continue | Await:
        """`gate_review`: hand the block to the auto-operator, or halt for a human.

        Reached when the loop exhausts its budget or the settlement reports a finding
        unresolvable. Both are real: an unsatisfiable finding may need a product decision
        that no amount of re-applying will produce.
        """
        if review_blocks >= self.MAX_REVIEW_BLOCKS:
            raise WorkflowFailed(
                f"the review for story {self.ctx.story_slug!r} was still blocked after "
                f"{review_blocks} operator resolution(s); giving up rather than looping. "
                f"Last block: {notes or '(no notes given)'}"
            )
        review_blocks += 1
        if self.operator_mode in {"human", "operator"}:
            return Await(
                self._context,
                self._escalation(notes, review_blocks).body,
                self.read_operator,
                notes=notes,
                code_review=code_review,
                code_reuse=code_reuse,
                review_blocks=review_blocks,
            )
        return Continue(
            result,
            self.resolve_review,
            notes=notes,
            code_review=code_review,
            code_reuse=code_reuse,
            review_blocks=review_blocks,
        )

    # --- the operator arm ---------------------------------------------------

    def resolve_review(
        self,
        notes: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_blocks: int = 0,
    ) -> Continue | Await:
        """Stand in for the operator on the unresolved findings, or escalate to a human.

        `resolve_review` + the `await_operator_review` that followed it unconditionally; see
        the module docstring. The resolver makes the call a human would — the product
        decision, or the targeted fix — and writes it into the story's `context.md`, so the
        human path is the automatic fallback rather than a separate mode.
        """
        self.logger.info("resolving the review block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # high, and unbounded: standing in for a human, with full tool access, on a
            # finding nobody else could settle.
            power="high",
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "block_kind": "review",
                "block_notes": notes,
            },
        )
        if result.decision == "answered":
            return Continue(
                result,
                self.read_operator,
                notes=notes,
                code_review=code_review,
                code_reuse=code_reuse,
                review_blocks=review_blocks,
            )
        # See `dev.flow.resolve_plan`: the escalating resolver's note is already in this
        # file and `Await` writes over it, so the body handed here carries that note
        # forward along with what the resolver tried.
        return Await(
            self._context,
            self._escalation(notes, review_blocks, result).body,
            self.read_operator,
            notes=notes,
            code_review=code_review,
            code_reuse=code_reuse,
            review_blocks=review_blocks,
        )

    def read_operator(
        self,
        notes: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_blocks: int = 0,
    ) -> Continue:
        """Consume the answer and apply it as the work.

        The consume half of `await_operator.py`. Unlike `dev`'s copy there is no scope
        branch: `await_operator_review` went to `apply_review_resolved` unconditionally, so
        an epic-scoped answer to a review block is applied as a story-level fix. Preserved
        rather than harmonised, and recorded as a finding — the two gates genuinely differ.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        return Continue(
            answer,
            self.apply_resolved,
            notes=notes,
            operator_context=answer.content,
            code_review=code_review,
            code_reuse=code_reuse,
            review_blocks=review_blocks,
        )

    def apply_resolved(
        self,
        notes: str,
        operator_context: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_blocks: int = 0,
    ) -> Continue:
        """Apply the operator's resolution, then start the review over with a fresh budget.

        `apply_review_resolved` + `reset_review`. Going back to `start` re-runs both feeder
        reviews against the new code, which is what the YAML did and what makes the answer
        binding rather than asserted: the same reviewer has to look again.
        """
        result = self.agent(
            "prompts/apply-review.md",
            returns=ImplResult,
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": notes,
                "operator_feedback": operator_context,
            },
        )
        return Continue(result, self.start, review_blocks=review_blocks)

    # --- the non-blocking feedback checkpoint -------------------------------

    def poll_feedback(
        self,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_rework: int,
        review_blocks: int = 0,
    ) -> Continue | Done:
        """Did a human drop a note into the run's inbox while the run was busy?

        `check_impl_feedback` + `decide_impl_feedback`. Never halts and never asks: polling
        the inbox replies to the oldest outstanding message, so one drop buys exactly one
        rework pass. No feedback — the common case — ends the flow and the caller proceeds
        to QA.
        """
        feedback = self.call(check_feedback, str(self.run_dir))
        if not feedback.present:
            return Done(ReviewResult())
        self.logger.info("operator feedback found — one rework pass", extra={"activity": True})
        return Continue(
            feedback,
            self.apply_feedback,
            content=feedback.content,
            code_review=code_review,
            code_reuse=code_reuse,
            review_rework=review_rework,
            review_blocks=review_blocks,
        )

    def apply_feedback(
        self,
        content: str,
        code_review: CodeReviewResult,
        code_reuse: CodeReuseResult,
        review_rework: int,
        review_blocks: int = 0,
    ) -> Continue:
        """Rework against the operator's notes, then re-review.

        No review findings go in: the feedback *is* the work, and handing the applier a stale
        set of already-settled findings would invite it to redo them. The rework counter is
        carried rather than reset, which is the YAML's wiring — the feedback pass re-enters
        the review loop with whatever allowance is left.
        """
        result = self.agent(
            "prompts/apply-review.md",
            returns=ImplResult,
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": "",
                "operator_feedback": content,
            },
        )
        return Continue(
            result,
            self.review,
            code_review=code_review,
            code_reuse=code_reuse,
            review_rework=review_rework,
            review_blocks=review_blocks,
        )

    # --- shared -------------------------------------------------------------

    @property
    def _docs_repo(self) -> str:
        """The docs repo, and the cwd of the three review turns."""
        return self.output(resolve_review_context).docs_repo_path

    @property
    def _repos(self) -> list[str]:
        """The code repos this story touched, which are what the reviewers may read."""
        return list(self.output(resolve_review_context).affected_repo_paths)

    @property
    def _context(self) -> Path:
        """The file an `Await` writes its questions into: `<story-folder>/context.md`."""
        return paths.story_context_path(self.ctx.story_path)

    def _escalation(
        self, notes: str, review_blocks: int, result: OperatorResolution | None = None
    ) -> OperatorGate:
        """The gate body for a review block — see `coder.shared.escalation`."""
        return self.call(
            compose_escalation,
            story_path=self.ctx.story_path,
            story_slug=self.ctx.story_slug,
            spec_dir=self.ctx.spec_dir,
            run_dir=str(self.run_dir),
            number=review_blocks,
            block_kind="review",
            block_notes=notes,
            where="the implementation-review stage",
            tried=list(result.tried) if result else [],
            summary=result.summary if result else "",
        )

    def _dirs(self) -> list[str]:
        """Every directory this run's agent turns may read."""
        return list(self.output(resolve_workspace_dirs).dirs)


__all__ = ["Review"]
