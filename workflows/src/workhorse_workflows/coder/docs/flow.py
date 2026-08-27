"""Fold a finished story into the as-built OKF book, and refuse to believe it was.

Reached from the main graph at four call sites (`docs`, `final_docs`, `failed_docs` and
the fix lane's per-item documentation pass), and standalone as `workhorse-coder run
docs`::

    detect OKF → classify context → document ⇄ (grounding gate → review) → passed

**The `document → verify → review` split is not cosmetic.** The author turn is the expensive
thing in the loop and the checkpoint is written before a state runs, so a resume after a
failed gate re-enters at the gate rather than re-documenting.

Shapes worth naming before reading the states:

* **Two rework budgets, not one.** `rework`/`MAX_REWORKS` counts the grounding gate's
  passes and `review_rework`/`MAX_REVIEW_REWORKS` the reviewer's revisions; `_rework`
  carries the run that forced the split. A gate that keeps failing on a different ground
  each pass is not the same thing as a reviewer asking for one more edit.
* **A budget exhaustion blocks; a malformed input fails.** `verify`'s grounding gate not
  converging in `MAX_REWORKS` passes takes the same `_blocked` arm as `review`'s own
  convergence exhaustion. The remaining raises guard inputs no repair lap can fix: an
  unresolvable story path, an unusable OKF, an author or reviewer response that does not
  parse.
* **In `semantic` mode the two context statuses are passed as `""`**, which is not a
  stand-in for `"invalid"`: `verify_story_documentation` reads them only in `local` mode,
  and passing `"invalid"` would look the same today and be wrong the moment the gate
  started reading them.
* **`blocked` consults before it ends the flow.** A documentation block is a product
  decision nobody ratified, and on a product the author workflow specified there is no
  human upstream of it — so `_blocked` spends one resolver turn in the author's stead and
  gives the story a repair lap on the answer. See `_blocked` for the loop guard and for
  what `human`/`operator` mode still does.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import AgentTimeout, Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.dev import (
    plan_summary,
    read_operator_context,
    resolve_impl_context,
)
from workhorse_workflows.coder.shared.docs import (
    MAX_PROMPT_NOTE_CHARS,
    classify_documentation_context,
    detect_okf_docs,
    documentation_obligations,
    features_root,
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.conversation import backbone
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.docs import (
    ContextClassification,
    DocsLoop,
    DocsProgress,
    DocsResult,
    DocumentationFinding,
    DocumentationObligations,
    DocumentationResult,
    DocumentationReview,
    RepairOverran,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels

#: No wall-clock bound on the resolver turn, for the reason `qa` gives at its own gate:
#: it is standing in for the accountable party, and cutting it off mid-decision buys a
#: block back.
UNBOUNDED = float("inf")

#: What the next repair turn is told when the one before it was cut at its wall-clock cap.
#: Prefixed to the gate notes by `_overran`, in the wording the QA lane already uses for the
#: same situation: a cut is not a defect in what landed, so the brief stays "continue", and
#: the errors underneath it are whatever doctor last reported.
_OVERRAN_REPAIR = (
    "Your previous turn was stopped at its wall-clock budget; continue from where you "
    "were — the errors below are what is still red."
)


def _overran_brief(gate_notes: str) -> str:
    """Prefix the standing rework brief with the cut, without stacking prefixes.

    A story can overrun twice against the same gate notes, and a brief that opened with two
    copies of the same paragraph would spend the turn's first attention on a repetition.
    """
    standing = gate_notes.removeprefix(_OVERRAN_REPAIR).strip()
    return f"{_OVERRAN_REPAIR}\n\n{standing}".strip() if standing else _OVERRAN_REPAIR


def _prompt_note(note: str) -> str:
    """Last-resort bound on a brief that would not fit an argv.

    A backstop, and it should no longer fire: the gate spills an over-long doctor-error
    list to a file and hands over the path instead, so the turn keeps the whole worklist.
    A note that arrives here oversized anyway is one this flow carried forward from an
    older checkpoint.
    """
    if len(note) <= MAX_PROMPT_NOTE_CHARS:
        return note
    return (
        note[:MAX_PROMPT_NOTE_CHARS].rstrip()
        + "\n\n... note truncated for the agent prompt; re-run `ostler doctor` yourself for "
        "the rest."
    )


class Docs(Workflow):
    """Document one story against the OKF graph, and gate the claim against the diff."""

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
    #: `local` or `dev` — passed through to the impl-context decode, which uses it to decide
    #: whether `-local` QA skills survive.
    target_env: str = "local"
    #: `snapshot_worktree_state`'s reading from before this story's first dev turn — the
    #: paths that were already dirty then, with their bytes. The grounding gate subtracts
    #: the ones that still match, so an earlier story's abandoned work is not charged to
    #: this one. Empty subtracts nothing, which is the pre-snapshot behaviour.
    preexisting: tuple[str, ...] = ()
    #: `auto`, `operator` or `human` — who answers a documentation block. `auto` spends one
    #: resolver turn standing in for the author that wrote this product's specs; the other
    #: two park on the driver's `Await` and wait for a person. See `_blocked`.
    operator_mode: str = "auto"

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Grounding-gate failures before the flow blocks. A `ClassVar` rather than an input:
    #: it is not an operator control.
    MAX_REWORKS: ClassVar[int] = 3

    #: Reviewer revisions before the flow fails, counted on their own. See `_rework`
    #: for the run that forced the split.
    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    #: Trips through the author gate that get a resolver turn before every further block
    #: goes straight to the caller — not a cap on how many times documentation may block;
    #: there isn't one. Each trip buys the reviewer a fresh budget, so this is what bounds
    #: the repair-and-block pair. See `_blocked`.
    MAX_DOCS_BLOCKS: ClassVar[int] = 3

    #: Repair laps that ride one session chain before it is started over. A chain is worth
    #: keeping because lap N+1 already knows what lap N edited and why; past a handful of
    #: laps that value is mostly compaction summary, and a conversation that has been
    #: wrong four times running is a worse starting point than an empty one.
    MAX_CHAIN_LAPS: ClassVar[int] = 4

    #: Repair turns cut at their wall-clock budget before the story escalates. A cut turn is
    #: re-dispatched rather than gated, so without a bound a repair that cannot finish inside
    #: 45 minutes would be re-dispatched forever; with one, the run walks toward the author
    #: gate — which is what a turn that reliably overruns is: a story too large to document
    #: in one pass, and a decision nobody has made yet.
    MAX_REPAIR_OVERRUNS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories.

        This lane names the story's backbone key like every other lane, but it does not
        inherit what is under it: `start` drops both chains before the first turn — see
        `_reset_chains` for the contamination that forced it.
        """
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    @property
    def _chain(self) -> str:
        """The session chain `repair` runs on, keyed per story.

        Per story rather than per run: a run documents several stories, and a chain they
        shared would open story two's repair on story one's diff — the failure the chain
        exists to avoid, inverted.
        """
        return f"docs-repair:{self.ctx.story_slug}"

    def _reset_chains(self) -> None:
        """Drop both chains this flow's turns run on for the current story.

        The repair chain, and the story backbone the author turn runs on. Dropping the
        backbone is the part that is not obvious: every other lane joins it on purpose, to
        reach the implementer that already read the code. Documentation re-entry is where
        that stops paying. A docs pass runs again after a fix, after an operator answer,
        after a resume — and the conversation it would resume describes a book and a set of
        commits that have both been rewritten since, so the author no-ops on edits it
        remembers making to a tree that no longer holds them. A cold turn re-reads the book
        in front of it, which is the answer that is actually true.
        """
        self.reset_session(backbone(self))
        self.reset_session(self._chain)

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's repair chain with it.

        Every terminal goes through here so no exit can forget: a chain left behind is a
        conversation about a book as it was, waiting for the next entry to resume it. The
        backbone chain is the exception: it is left open for whatever lane runs next in
        this run, which finds it under the same story-derived key.
        """
        self.reset_session(self._chain)
        return Done(result)

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on, what each gate
        last decided, and whether the pass that decided it bought anything.

        The two rework budgets are split because the grounding gate and the reviewer fail
        for unrelated reasons — see `_rework`. Which one a story spent is the whole point of
        keeping them apart, and it is invisible unless both are labelled.

        A verdict labels the spans opened *after* it — the author turn a `revise` forced,
        not the review turn that said the word. That is the useful direction, and the same
        one `Qa.state_labels` documents: it lets a query attribute the cost of a rework to
        the verdict that caused it. It is also why `_rework` carries the progress forward
        rather than dropping it at the transition — `groom profile` aggregates agent-turn
        spans only, and `verify` spends no turn, so a gate verdict is visible exactly
        because the next author turn inherits it.

        `setup` and the first entry to `start` run before any loop exists, and report
        nothing but the story.
        """
        loop = params.get("loop")
        if not isinstance(loop, DocsLoop):
            return self.labels()
        carried = loop.progress.model_dump()
        return (
            self.labels()
            | counter_labels(loop.model_dump(), "docs", DocsLoop.COUNT_LABELS)
            | counter_labels(carried, "docs", DocsProgress.COUNT_LABELS)
            | verdict_labels(carried, "docs", DocsProgress.VERDICT_LABELS)
        )

    def start(self) -> Continue | Done:
        """Decide whether there is a book to document into, and how the diff can be read.

        The three OKF arms are genuinely distinct: `no` ends the flow successfully — most
        repos the coder runs against are not managed by an OKF graph and there is nothing to
        document into — while `invalid` fails it, because a graph that is configured and will
        not load is a broken repo rather than an unmanaged one.

        A classification of `error` fails here for the same reason. It says the worktree
        could not be read at all, which is not a mode to gate in: `semantic` would turn the
        grounding gate off and report a story documented on the strength of prose nobody
        checked against the code.
        """
        # Whatever is left of an earlier pass describes a book and a diff that have both
        # moved since. Entry is the one place that is knowable.
        self._reset_chains()
        if not self.ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r} — the story could not be resolved, so "
                "there is nothing to document."
            )
        impl = self.call(
            resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path
        )
        okf = self.call(detect_okf_docs, self.docs_path)
        if okf.has_okf == "no":
            self.logger.info("no OKF docs here — nothing to document")
            return self._ends(DocsResult(status="not_applicable", notes=okf.reason))
        if okf.has_okf != "yes":
            raise WorkflowFailed(f"OKF documentation is unusable here: {okf.reason}")
        classification = self.call(
            classify_documentation_context, self.docs_path, tuple(impl.qa_source_roots)
        )
        if classification.mode == "error":
            raise WorkflowFailed(
                f"the documentation context could not be read: {classification.notes}"
            )
        # The grounding worklist, before the author turn rather than after it. The gate
        # computes the same join from the same packet; paying for it once here is what
        # keeps the author from re-deriving it by hand, which it does badly and at length.
        obligations = self._obligations(classification)
        return Continue(
            okf, self.document, loop=DocsLoop(obligations=tuple(obligations.refs))
        )

    def document(self, loop: DocsLoop) -> Continue | Await | Done:
        """Write the story into the book — the one agent turn this flow spends per pass.

        `not_required` is a real answer and proceeds to the gate exactly like `documented`
        does, because "this story changed nothing the book describes" is a claim the
        grounding gate can check. `blocked` is the third and last answer the contract
        admits: the author *did* speak, and what it said is that the book cannot be made
        true of this code. It comes back as a `blocked` `DocsResult` for the caller to
        place; see `Coder.blocked_docs` for why that is one story's finding rather than the
        whole run's.

        This state is the *first pass only*. A gate failure or a reviewer refusal goes to
        `repair`, which edits the nodes the findings cite instead of re-authoring the book.
        """
        self.logger.info("documenting %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "document-story")
        result = self.agent(
            turn.prompt,
            returns=DocumentationResult,
            # medium: folding a known change into an existing graph, against a schema and a
            # gate that will check the result. Not a discovery task.
            power="medium",
            session=backbone(self),
            add_dirs=workspace_dirs(self),
            args=turn.args | self._author_args(loop),
        )
        return self._authored(result, loop)

    def repair(self, loop: DocsLoop) -> Continue | Await | Done:
        """Edit the nodes the findings cite, and leave every other node alone.

        Every pass after the first used to re-enter `document`, whose brief is "write this
        story into the book". Handed that instruction plus a finding against one bullet, the
        author revisits nodes nobody complained about — so the `power="high"` reviewer meets a
        changed book each round and, correctly, finds a different real defect in it. That is
        the loop `document-story` averaged 4.5 turns on. Bounding the reviewer's scope (its
        own prompt) only helps if the artifact under review stops moving underneath it, which
        is what this state is for.

        Same brief, same result, same gate as `document`: only the instruction and the
        power tier differ.

        The laps also share one conversation. Under a clean context per turn, lap N+1 is
        handed a worklist and has to re-read the nodes lap N was editing a minute earlier
        before it can act on it — a turn of reading bought to end up with a worse copy of
        the context the model just had. The chain is dropped when it stops being an asset:
        after `MAX_CHAIN_LAPS`, and on a `stalled` gate verdict, which says the last laps
        changed nothing and the conversation has talked itself into a corner.

        The turn is capped at 45 minutes. It iterates doctor itself over a worklist that can
        be the whole story's ungrounded set, so it is not a turn that can be sized by its
        instruction — but without a bound it inherits the run's watchdog and a single lap
        can eat an hour. `retries=0`, because a retry would restart the turn against a book
        its own first attempt already edited; what a cut turn gets instead is `_overran`.
        """
        self.logger.info("repairing the documentation for %s", self.ctx.story_slug,
                         extra={"activity": True})
        laps = loop.progress.chain_laps
        if laps >= self.MAX_CHAIN_LAPS or loop.progress.gate_progress_verdict == "stalled":
            self.reset_session(self._chain)
            laps = 0
        loop = loop.model_copy(
            update={"progress": loop.progress.model_copy(update={"chain_laps": laps + 1})}
        )
        try:
            turn = roles.turn(self, "repair-documentation")
            result = self.agent(
                turn.prompt,
                returns=DocumentationResult,
                # low: applying a named list of edits to nodes that already exist. Paying the
                # authoring tier for it is part of what tempted the turn to re-author.
                power="low",
                # 45 min, and `retries=0` — see the docstring. A retry would restart the turn
                # against a book its own first attempt already edited.
                timeout=2700,
                retries=0,
                add_dirs=workspace_dirs(self),
                args=turn.args | self._author_args(loop),
                session=self._chain,
            )
        except AgentTimeout:
            return self._overran(loop)
        return self._authored(result, loop)

    def _overran(self, loop: DocsLoop) -> Continue | Await | Done:
        """Re-dispatch a repair turn that was cut at its wall-clock budget.

        The turn produced no reply, so nothing was authored and no status was returned. This
        state used to write one anyway — a `DocumentationResult(status="documented")` the
        flow minted itself — and hand it to the gate. In `semantic` mode, where the gate has
        no worktree to check the claim against, that word is the *only* evidence there is,
        and it went into the story's record as the author's. Downstream QA reads it as a
        story that is in the book. A turn stopped mid-edit said no such thing.

        So the outcome recorded is `overran`, which is a thing Python observed rather than a
        claim about the book, and the same repair is dispatched again — on a fresh chain,
        because the conversation that ran out of clock is the one thing known not to be
        converging, and told through `gate_notes` that its own worklist is half-applied. The
        worklist itself is unchanged: doctor still reports whatever is still red.

        A turn that reliably overruns walks to the author gate rather than lapping: past
        `MAX_REPAIR_OVERRUNS` the story is too large to document in one pass, which is a
        decision, not a defect. `_blocked` is the same arm every other exhausted docs budget
        takes.
        """
        overruns = loop.overruns + 1
        self.logger.info(
            "the documentation repair turn was stopped at its budget (%d of %d) — "
            "starting it over on a fresh conversation",
            overruns,
            self.MAX_REPAIR_OVERRUNS,
            extra={"activity": True},
        )
        loop = loop.model_copy(update={"overruns": overruns})
        if overruns >= self.MAX_REPAIR_OVERRUNS:
            return self._blocked(
                f"the documentation repair turn was cut at its wall-clock budget "
                f"{overruns} times and never finished a pass — the story's ungrounded set "
                f"is too large to repair in one turn.",
                loop,
            )
        self.reset_session(self._chain)
        return Continue(
            RepairOverran(lap=overruns, notes=_OVERRAN_REPAIR),
            self.repair,
            loop=loop.model_copy(
                update={
                    "gate_notes": _overran_brief(loop.gate_notes),
                    # The chain it would have counted against is gone.
                    "progress": loop.progress.model_copy(update={"chain_laps": 0}),
                }
            ),
        )

    def _author_args(self, loop: DocsLoop) -> dict[str, object]:
        """The brief `document` and `repair` share — same inputs, different instruction."""
        classification = self.output(classify_documentation_context)
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "epic": self.epic,
            "docs_path": self.docs_path,
            "features_root": features_root(self),
            "epic_path": self._epic_path,
            "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
            "context_mode": classification.mode,
            "context_notes": classification.notes,
            "gate_notes": _prompt_note(loop.gate_notes),
            "review_notes": _prompt_note(loop.review_notes),
            "obligations": list(loop.obligations),
        }

    def _authored(
        self, result: DocumentationResult, loop: DocsLoop
    ) -> Continue | Await | Done:
        """The tail both author turns share: the contract on the answer, then the gate.

        The nodes accumulate across passes rather than being replaced by the last one's.
        `repair`'s brief is "edit the nodes these findings cite", so a lap that correctly
        concludes the finding needs no edit — the cited symbol was deleted, or is already
        grounded elsewhere — honestly returns `documented` with an empty node list. Scoring
        the gate on that one lap read it as an author that had named nothing and failed the
        story on a check meant for an author that never spoke. That is what ended a real
        run: four grounding passes of work discarded on the pass that had nothing left to
        do.
        """
        # `blocked` on the derived property, not the literal: an author that answered
        # `unfixable` or `invalid` said the same thing, and one arm should not turn on
        # which synonym it reached for.
        if result.blocked:
            self.logger.info(
                "documentation author blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            return self._blocked(result.notes, loop)
        return Continue(
            result,
            self.verify,
            author=result,
            loop=loop.model_copy(
                update={
                    "authored_nodes": tuple(
                        dict.fromkeys((*loop.authored_nodes, *result.nodes))
                    )
                }
            ),
        )

    def verify(
        self, author: DocumentationResult, loop: DocsLoop
    ) -> Continue | Await | Done:
        """Check the claim against the diff before any reviewer reads a word of it.

        In `local` mode the diff is mapped onto the graph deterministically and the gate
        demands *direct* grounding for every changed production unit. In `semantic` mode
        there is no worktree to diff against, so the packet is skipped and doctor plus the
        review turn is the authority. Nothing but an explicit pass reaches the reviewer.
        """
        classification = self.output(classify_documentation_context)
        mode = classification.mode
        if mode == "error":
            raise WorkflowFailed(
                f"the documentation context could not be read: {classification.notes}"
            )
        build_status: Literal["", "passed", "invalid"] = ""
        validate_status: Literal["", "passed", "invalid"] = ""
        if mode == "local":
            build = self._okf_packet(classification)
            build_status = build.status
            validate_status = self.call(
                validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path
            ).status

        gate = self.call(
            verify_story_documentation,
            self.docs_path,
            self.ctx.spec_dir,
            author.status,
            build_status,
            validate_status,
            mode,
            # Every node any pass named, not only this one's — see `_authored`.
            loop.authored_nodes,
            preexisting=tuple(self.preexisting),
        )
        loop = loop.model_copy(update={"progress": loop.progress.after_gate(gate)})
        if gate.status == "passed":
            # The worklist empties with the gate that closed it: `obligations` is what the
            # author still owes, and a pass means nothing. A reviewer-driven repair lap
            # downstream of here must not re-open items the gate already ratified.
            return Continue(
                gate,
                self.review,
                author=author,
                loop=loop.model_copy(
                    update={"gate_notes": gate.notes, "obligations": ()}
                ),
            )
        notes = gate.notes
        # No escape hatch for a shrinking failure set. The gate used to waive the budget
        # while `gate_progress_verdict == "reduced"`, which is exactly the shape a batched
        # worklist produces — twelve errors closed per lap out of a hundred and twenty,
        # forever. The repair turn now gets every affected error at once and iterates
        # doctor itself, so a lap that does not converge is a lap that is not going to —
        # which is a block, not a failure: `_blocked` below, the same arm `review`'s own
        # convergence exhaustion takes a few lines down. A workflow does not give up.
        if loop.rework >= self.MAX_REWORKS:
            return self._blocked(
                (
                    f"documentation did not converge in {self.MAX_REWORKS + 1} grounding "
                    f"passes ({loop.progress.gate_progress_verdict}): "
                    f"{gate.notes or loop.review_notes}"
                ),
                loop.model_copy(update={"gate_notes": notes}),
            )
        # The `G:` identities are the still-ungrounded references, in the inventory's own
        # spelling — the same worklist `start` computed, minus what this pass closed.
        return self._rework(
            gate,
            loop.model_copy(
                update={
                    "rework": loop.rework + 1,
                    "gate_notes": notes,
                    "obligations": tuple(
                        failure[2:]
                        for failure in gate.failures
                        if failure.startswith("G:")
                    ),
                }
            ),
        )

    def review(
        self, author: DocumentationResult, loop: DocsLoop
    ) -> Continue | Await | Done:
        """An independent read of what was written, downstream of a gate it cannot bypass.

        `blocked` ends the flow — the reviewer is saying the story cannot be documented as
        it stands, which no number of rework passes will change — but it ends it with a
        verdict rather than a failure, for the reason `document` gives. `revise` spends a
        rework instead.

        **Spending the last rework is the same answer, not a worse one.** A reviewer still
        saying `revise` on the final pass is a reviewer saying the book cannot be made true
        of this code within this budget, which is what `blocked` means; raising instead
        killed the *run*. Returning `blocked` lets `Coder.blocked_docs` contain the finding
        to this story, including when a post-QA mutation made the final recheck mandatory.

        The scope the reviewer is handed is the *unnarrowed* worklist `start` computed, read
        back off the one record that holds it. `loop.obligations` shrinks as the gate closes
        items, which is right for an author being told what is left to do and wrong for a
        reviewer being told what this story is answerable for: a scope that shrinks every
        pass would keep re-legalizing the findings it had just ruled out of bounds.
        """
        turn = roles.turn(self, "review-story-documentation")
        result = self.agent(
            turn.prompt,
            returns=DocumentationReview,
            # high: judging whether prose describes the system as built is the harder half
            # of documenting it.
            power="high",
            add_dirs=workspace_dirs(self),
            args=turn.args | {
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "features_root": features_root(self),
                "epic_path": self._epic_path,
                "author_status": author.status,
                "author_notes": author.notes,
                "gate_notes": loop.gate_notes,
                "review_notes": loop.review_notes,
                "obligations": list(self.output(documentation_obligations).refs),
            },
        )
        if result.status == "approved":
            self.logger.info("documentation approved for %s", self.ctx.story_slug)
            return self._ends(
                DocsResult(
                    status="passed",
                    notes=result.notes,
                    authored_nodes=list(loop.authored_nodes),
                )
            )
        if result.blocked:
            self.logger.info(
                "documentation review blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            # A reviewer that refused still names what it read as wrong. Those findings are
            # what an operator needs to rule on, and without them the gate says only that
            # documentation is impossible, not which contradiction made it so.
            return self._blocked(result.notes, loop, findings=result.actionable)
        finding_problems = _review_finding_problems(result)
        if finding_problems:
            raise WorkflowFailed(
                "documentation reviewer requested revisions with invalid structured findings: "
                + "; ".join(finding_problems)
            )
        # After the structural check, so a malformed `revise` still fails on its findings
        # rather than being scored on them.
        loop = loop.model_copy(update={"progress": loop.progress.after_review(result)})
        notes = _review_notes(result)
        if loop.review_rework >= self.MAX_REVIEW_REWORKS:
            self.logger.warning(
                "documentation review did not converge for %s in %d passes — blocking: %s",
                self.ctx.story_slug,
                self.MAX_REVIEW_REWORKS + 1,
                notes,
            )
            return self._blocked(
                (
                    f"documentation review did not converge in "
                    f"{self.MAX_REVIEW_REWORKS + 1} passes "
                    f"({loop.progress.review_progress_verdict}): "
                    f"{notes or loop.gate_notes or 'no notes'}"
                ),
                loop,
            )
        return self._rework(
            result,
            loop.model_copy(
                update={"review_rework": loop.review_rework + 1, "review_notes": notes}
            ),
        )

    def _rework(self, result: object, loop: DocsLoop) -> Continue:
        """Send the author back with what it must fix.

        Not a state — the routing half of a branch, called from the three sites that can
        decide the documentation is not good enough yet. `_`-prefixed so state discovery
        does not pick it up.

        **The two counters are deliberately separate.** The grounding gate is deterministic — it names
        the exact ungrounded symbols and converges in a pass or two — while
        `review_story_documentation` is a `power="high"` semantic read that finds a different
        real defect each round. Sharing one budget means a story that needed a single
        mechanical grounding fix arrives at the reviewer with two rounds left. That is how a
        two-language schema story died on a real run: one gate failure, then three reviewer
        refusals each naming a distinct, correct, fixable defect, and the flow raised on the
        third with the book one edit from conformant. Same defect the QA flow's
        `_guard_plan_validation` split fixes.

        Where it sends the author is `repair`, not `document`: a finding against three
        bullets is not a reason to rewrite the nodes the gate and the reviewer both passed.
        """
        return Continue(result, self.repair, loop=loop)

    # ── the author gate ───────────────────────────────────────────────────────────────

    def _blocked(
        self, notes: str, loop: DocsLoop, *, findings: Sequence[Finding] = ()
    ) -> Continue | Await | Done:
        """A block ends the flow — but not before the author it belongs to gets a say.

        The three sites that can refuse a story (the author turn, the reviewer, and a review
        loop that ran out of passes) all funnel through here, which is what makes it the
        right place to ask. A documentation block is almost never "the prose is wrong": it is
        the book and the code disagreeing about something nobody ever ratified — a contract
        the specs describe two ways, a guarantee the plan required and the implementation
        did not keep. Answering that is a *product* decision.

        On a product whose specs were themselves written by the author workflow, there is no
        human upstream of that decision to defer to. Parking the story until a person appears
        defers it to the only party with *less* context than the flow has, and costs every
        story behind it in the meantime — six of one epic's eight, on the run that forced
        this state. So in `auto` the resolver answers in the author's stead, and the story
        gets one more repair lap on the ratified answer.

        `MAX_DOCS_BLOCKS` caps the *resolver*, not the block, exactly as the other lanes
        cap theirs. Each consult buys the reviewer a fresh budget (`read_author` resets it
        explicitly), so the pair cannot cycle: the laps are bounded by the reset count, and
        the story walks toward a person once they are spent.

        `human`/`operator` mode still parks — someone asked to be asked.

        `findings` reaches the gate body but deliberately not `carried`: it is evidence for
        whoever reads the escalation, and putting it in the checkpoint would widen the
        state's parameters — which *are* the checkpoint — for a value nothing downstream
        reads.
        """
        if loop.blocks >= self.MAX_DOCS_BLOCKS:
            return self._ends(DocsResult(status="blocked", notes=notes))
        loop = loop.model_copy(update={"blocks": loop.blocks + 1})
        carried: dict[str, Any] = {"notes": notes, "loop": loop}
        if self.operator_mode in {"human", "operator"}:
            gate = escalation(
                self,
                block_kind="docs",
                where=f"the docs stage, after {loop.rework} rework pass(es)",
                notes=notes,
                number=loop.blocks,
                findings=findings,
            )
            return Await(context_path(self), gate.body, self.read_author, **carried)
        return Continue(None, self.resolve_author, **carried)

    def resolve_author(self, notes: str, loop: DocsLoop) -> Continue | Done:
        """Stand in for the author who wrote the specs, and ratify what the book contradicts.

        The same resolver `qa`, `dev` and `review` reach, on `block_kind="docs"`, and this
        is the lane whose answering arm was never removed — the port kept it because a docs
        block is so often a question the documents themselves already answer. What the
        resolver may answer *from* is written down (`shared/resolution.py`): a decision
        record, a repo rule, an installed skill, an acceptance criterion. Having done so it
        amends the authored documents, so the decision is the product's and not this run's.

        An escalation ends the flow blocked rather than waiting, for the reason
        `Qa.resolve_operator` gives: the story drain is single-threaded, so a parked story
        parks every epic behind it. The block is not silent: it surfaces as the run's own
        failure, carrying its reason, which is what an operator polls for.
        """
        self.logger.info("resolving the documentation block", extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: the same reasoning `qa` documents — standing in for the
            # accountable party, with full tool access, on the flow's costliest decision.
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=workspace_dirs(self),
            args=resolver_args(
                self, block_kind="docs", notes=notes, docs_path=self.docs_path
            ),
        )
        if not answered(self, result, "docs"):
            self.logger.info("the documentation resolver escalated — blocking the story")
            return self._ends(DocsResult(status="blocked", notes=notes))
        return Continue(result, self.read_author, notes=notes, loop=loop)

    def read_author(self, notes: str, loop: DocsLoop) -> Continue | Done:
        """Take the ratified decision off `context.md` and spend one repair lap on it.

        An unanswered file ends the flow blocked. Both arms into this state believe an
        answer landed — the resolver said `answered`, or the driver's `Await` returned
        because the file was touched — so a file that says otherwise means the answer was
        never written, and re-entering the loop with the empty brief would spend a repair
        lap on a ratification nobody made.

        An `epic`-scoped answer is not something this flow can act on either — it says the
        epic's premise was wrong, which no edit to one story's documentation reaches — so it
        comes back as the block's verdict, carrying the answer as the notes
        `Coder.blocked_docs` puts into the failure.

        The reviewer's budget resets. It was spent arguing about a question that had no
        ratified answer; now there is one, and re-entering with nothing left to spend would
        block again on the next pass without the author ever seeing it. The reset is written
        down rather than implied by omission, and `MAX_DOCS_BLOCKS` is what bounds how many
        times it can happen.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if not answer.answered:
            self.logger.warning(
                "no answer landed on the context file for %s — blocking the story",
                self.ctx.story_slug,
            )
            return self._ends(DocsResult(status="blocked", notes=notes))
        if answer.scope == "epic":
            self.logger.info("the author scoped the documentation block to the epic")
            return self._ends(DocsResult(status="blocked", notes=answer.content or notes))
        brief = "\n".join(
            part for part in (f"Ratified by the author: {answer.content}".strip(), notes) if part
        )
        return self._rework(
            answer,
            loop.model_copy(update={"review_rework": 0, "review_notes": brief}),
        )

    def _okf_packet(self, classification: ContextClassification) -> OkfContextResult:
        """Map this story's code diff onto the OKF graph, and write the packet beside it.

        `_obligations` and `verify` both want it — the *before* picture and the *after* one
        — and the eight arguments that say which diff and which graph are the same both
        times. Spelling them twice is how the two pictures drift apart.
        """
        return self.call(
            build_okf_context,
            self.ctx.spec_dir,
            self.ctx.story_path,
            features_root(self),
            tuple(classification.source_roots),
            "HEAD",
            "WORKTREE",
            self.docs_path,
            preexisting=tuple(self.preexisting),
        )

    def _obligations(self, classification: ContextClassification) -> DocumentationObligations:
        """Build the diff packet and read the grounding worklist off it, before authoring.

        `local` mode only: `semantic` mode has no worktree to diff, and the node says so
        rather than returning an empty worklist that would read as "nothing to ground".
        The packet is rebuilt in `verify` against the tree the author left behind — this
        one is the *before* picture and is deliberately not reused as the gate's input.
        """
        build_status = ""
        if classification.mode == "local":
            build_status = self._okf_packet(classification).status
        return self.call(
            documentation_obligations,
            self.docs_path,
            self.ctx.spec_dir,
            classification.mode,
            build_status,
            preexisting=tuple(self.preexisting),
        )

    @property
    def _epic_path(self) -> str:
        """The parent epic whose user journeys this story advances."""
        root = Path(find_docs_root(self.docs_path, self.repo_dir))
        return f"{paths.epic_dir_rel(root, self.ctx.story_epic)}/epic.md"

def _format_finding(finding: DocumentationFinding) -> str:
    """One structured reviewer finding as the repair prompt's line protocol."""
    issue = finding.issue.rstrip(".")
    return f"{finding.id} [{finding.kind}] {finding.target}: {issue}. Repair: {finding.repair}"


def _review_finding_problems(review: DocumentationReview) -> list[str]:
    """Why a revision response is not an actionable, stable repair contract.

    A finding's `id` is an **opaque handle**, checked for presence and nothing else. Its
    only job is to name the same defect across passes so `_review_notes` can carry a
    stable worklist back to the author — no consumer parses it, and the shape the prompt
    suggests (`D1`) is a convention, not a contract. Enforcing that shape cost a whole
    real run: a reviewer returned two correct, fully actionable findings labelled
    `F1`/`F2`, and the format check turned a routine revise pass into `WorkflowFailed`,
    discarding an hour of context over a prefix letter.
    """
    if review.status != "revise":
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


def _review_notes(review: DocumentationReview) -> str:
    """The repair brief: structured findings first, summary second."""
    lines = [_format_finding(finding) for finding in review.findings]
    if review.notes:
        lines.append(f"Summary: {review.notes}")
    return "\n".join(lines)


__all__ = ["Docs"]
