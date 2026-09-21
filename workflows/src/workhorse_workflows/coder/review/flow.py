"""Review a story's implementation and drive the findings to settled."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.conversation import spend_turn, story_chain
from workhorse_workflows.coder.shared.dev import (
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

UNBOUNDED = float("inf")

MAX_SESSION_TURNS = 8

MUST_FIX_CONFIDENCE = 80


def split_on_confidence(
    findings: Sequence[ReviewFinding],
) -> tuple[list[ReviewFinding], list[ReviewFinding]]:
    """Split code-review findings into the mandatory ones and the advisory ones."""
    must_fix = [f for f in findings if f.score >= MUST_FIX_CONFIDENCE]
    advisory = [f for f in findings if f.score < MUST_FIX_CONFIDENCE]
    return must_fix, advisory


def findings_block(findings: Sequence[ReviewFinding]) -> str:
    """Render findings as the markdown the review prompt inlines, or `None.` for an empty set."""
    if not findings:
        return "None."
    return "\n".join(
        f"- **{f.target}** — {f.issue}\n"
        f"  - Category: {f.category} (confidence {f.score})\n"
        f"  - Required fix: {f.repair}"
        for f in findings
    )


def require_story_file(ctx: StoryPaths) -> None:
    """Fail the run when the slug did not resolve to a story file that exists."""
    if not ctx.story_path or not Path(ctx.story_path).is_file():
        raise WorkflowFailed(
            f"story '{ctx.story_slug}' did not resolve to a story file "
            f"({ctx.story_path or 'no path'}); nothing to review."
        )


class Review(Workflow):
    """Review one story's implementation, and settle every finding it raises."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    repo: str = ""
    branch: str = ""
    pr_number: str = ""
    inherited_turns: int = 0


    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    MAX_REVIEW_BLOCKS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths, the workspace to directories, and the repos to review."""
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        require_story_file(ctx)
        self.call(resolve_review_context, ctx.spec_dir, self.repo, self.docs_path)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which review round the next state is on."""
        loop = params.get("loop")
        if not isinstance(loop, ReviewLoop):
            return self.labels()
        return self.labels() | counter_labels(
            loop.model_dump(), "review", ReviewLoop.COUNT_LABELS
        )


    def start(self, loop: ReviewLoop | None = None) -> Continue | Await:
        """Review the diff — bugs, the coding standard, and reuse — in one pass."""
        lap = loop or ReviewLoop(session_turns=self.inherited_turns)
        self.logger.info("reviewing %s", self.ctx.story_slug, extra={"activity": True})
        self.call(clear_review_resolution, self.ctx.spec_dir, self.ctx.story_slug)
        self.reset_session(self._feeder_chain)
        turn = roles.turn(self, "code-review", returns=CodeReviewResult)
        code_review = self.agent(
            turn.prompt,
            returns=turn.returns,
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
            return self._gate(
                code_review,
                code_review.findings_summary or "the code-review pass could not read the diff",
                lap,
                where="the code-review pass",
            )
        return Continue(code_review, self.review, code_review=code_review, loop=lap)


    def review(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Review the implementation against the story, and route on the verdict."""
        must_fix, advisory = split_on_confidence(code_review.findings)
        turn = roles.turn(self, "review-implementation", returns=ReviewVerdict)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            cwd=self._docs_repo,
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_slug": self.ctx.story_slug,
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "affected_repo_paths": self._repos,
                "must_fix_findings": findings_block(must_fix),
                "advisory_findings": findings_block(advisory),
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        if result.status == "approved":
            return Continue(result, self.poll_feedback, code_review=code_review, loop=loop)
        if result.blocked:
            return self._gate(result, result.notes, loop)
        return self._guard(result, result.notes, code_review, loop)

    def apply(
        self, notes: str, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Resolve the findings, then let ostler decide whether they are actually resolved."""
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
                "story_id": self.ctx.story_id or self.ctx.story_slug,
                "epic": self.epic,
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "review_notes": notes,
            },
        )
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
        """`guard_review`: another apply pass, or the operator."""
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
        """`gate_review`: hand the block to the resolver, or straight to a human."""
        if self.operator_mode in {"human", "operator"} or loop.blocks >= self.MAX_REVIEW_BLOCKS:
            gate = self._escalation(notes, loop.blocks, where=where)
            return Await(
                context_path(self), gate.body, self.read_operator, notes=notes, loop=loop
            )
        return Continue(result, self.resolve_review, notes=notes, loop=loop, where=where)


    def resolve_review(
        self,
        notes: str,
        loop: ReviewLoop,
        where: str = "the implementation-review stage",
    ) -> Continue | Await:
        """Resolve a review block from what is already written down, or park for the operator."""
        self.logger.info("resolving the review block", extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
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
        return Await(
            context_path(self),
            self._escalation(notes, loop.blocks, result, where=where).body,
            self.read_operator,
            notes=notes,
            loop=spent,
        )

    def read_operator(self, notes: str, loop: ReviewLoop) -> Continue:
        """Consume the answer and apply it as the work."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        return Continue(answer, self.apply_resolved, notes=notes, loop=loop)

    def apply_resolved(self, notes: str, loop: ReviewLoop) -> Continue | Await:
        """Apply the operator's resolution, then start the review over with a fresh budget."""
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
                "story_id": self.ctx.story_id or self.ctx.story_slug,
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


    def poll_feedback(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Done:
        """Did a human drop a note into the run's inbox while the run was busy?"""
        feedback = self.call(check_feedback, str(self.run_dir))
        if not feedback.present:
            return Done(ReviewResult())
        self.logger.info("operator feedback found — one rework pass", extra={"activity": True})
        return Continue(feedback, self.apply_feedback, code_review=code_review, loop=loop)

    def apply_feedback(
        self, code_review: CodeReviewResult, loop: ReviewLoop
    ) -> Continue | Await:
        """Rework against the operator's notes, then re-review."""
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
                "story_id": self.ctx.story_id or self.ctx.story_slug,
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
        """The gate body for a block in this lane — see `coder.shared.escalation`."""
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
        """The code-review pass's own conversation — review-local by design."""
        return f"review-feeders:{self.ctx.story_slug}"

    def _apply_power(self) -> str:
        """How much reasoning an apply turn gets, given whose context it runs in."""
        return "low" if self.chain_session(self._impl_chain()) else "high"

    def _impl_chain(self) -> str:
        """The implementer's conversation, which the *apply* turns rejoin."""
        return story_chain(self.ctx.story_slug)

    def _spend_turn(self, loop: ReviewLoop) -> ReviewLoop:
        """Count one apply turn onto the implementer conversation, recycling it when full."""
        spent = spend_turn(
            self, self._impl_chain(), loop.session_turns, MAX_SESSION_TURNS
        )
        return loop.model_copy(update={"session_turns": spent})


__all__ = ["Review"]
