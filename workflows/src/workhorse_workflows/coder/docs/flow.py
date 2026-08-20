"""Fold a finished story into the as-built OKF book, and refuse to believe it was — the port
of `coder/workflow.yaml`'s `flows.docs` (22 nodes, lines 2176-2437).

Reached from the main graph at four call sites (`docs`, `final_docs`, `failed_docs` and
`document_fix_item`, the last through the `*docs_flow` anchor inside `flows.fix`), and
standalone as `workhorse-coder run docs`::

    detect OKF → classify context → document ⇄ (grounding gate → review) → passed

Twenty-two nodes become six states. Five are `type: branch` routers reading a value produced
directly above them, two are the `seed`/`incr` counter pair, and two are `emit-kv.py`
terminals — the YAML's way of returning a value, which is `Done(...)` here.

**The `document → verify → review` split is not cosmetic.** The author turn is the expensive
thing in the loop and the checkpoint is written before a state runs, so a resume after a
failed gate re-enters at the gate rather than re-documenting.

Divergences from the YAML, all deliberate:

* `documentation_rework_count` was a var with `seed`/`incr` nodes; it is the `rework`
  parameter, and the budget is `MAX_REWORKS` — the literal `"3"` on `guard_documentation`
  is the only budget the YAML had. **It is now two.** `review_rework`/`MAX_REVIEW_REWORKS`
  counts the reviewer's revisions separately from the grounding gate's; `_rework` carries
  the run that forced the split.
* **`documentation_failed` was a `type: fail`**, so every arm that reached it raised
  `WorkflowFailed` at the deciding site. What the four call sites' `default: failed` was for
  — a sub-flow that produced no value at all — cannot happen here, and `DocsResult`'s
  default records that. A workflow does not give up, though: the one arm here that was a
  rework-budget exhaustion rather than a genuinely malformed or unresolvable input —
  `verify`'s grounding gate not converging in `MAX_REWORKS` passes — now takes the same
  `_blocked` arm `review`'s own convergence exhaustion always did. The remaining raises
  guard inputs no repair lap can fix: an unresolvable story path, an unusable OKF, an
  author or reviewer response that does not parse.
* `resolve_documentation_context` reused `resolve-impl-context.py` whole and read only two
  of its seven outputs. It is the same `resolve_impl_context` node here; the port does not
  fork a node to narrow what a caller reads.
* the `output_key` argument that `build-qa-okf-context.py` and `validate-qa-okf-context.py`
  took (`"documentation_context_build"`, `"documentation_context_result"`) folds away —
  see `shared/okf.py`. The two nodes are shared with `qa`, which passed different names.
* in `semantic` mode the two context statuses are passed as `""`. That is not a stand-in for
  "invalid": under the YAML they were *unset vars*, which Jinja renders as the empty string,
  and `verify-story-documentation.py` only reads them in `local` mode. Passing `"invalid"`
  would look the same today and be wrong the moment the gate started reading them.

One shape is in neither the YAML nor the port it came from: **`blocked` consults before it
ends the flow**. A documentation block is a product decision nobody ratified, and on a
product the author workflow specified there is no human upstream of it — so `_blocked`
spends one resolver turn in the author's stead and gives the story a repair lap on the
answer. See `_blocked` for the loop guard and for what `human`/`operator` mode still does.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

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
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.escalation import escalation
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    resolver_args,
)
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.story import prepare_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.docs import (
    ContextClassification,
    DocsProgress,
    DocsResult,
    DocumentationFinding,
    DocumentationObligations,
    DocumentationResult,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels

#: No wall-clock bound on the resolver turn, for the reason `qa` gives at its own gate:
#: it is standing in for the accountable party, and cutting it off mid-decision buys a
#: block back.
UNBOUNDED = float("inf")

#: What the next repair turn is told when the one before it was cut at its wall-clock cap.
#: Prefixed to the gate notes by `verify`, in the wording the QA lane already uses for the
#: same situation: a cut is not a defect in what landed, so the brief stays "continue", and
#: the errors underneath it are whatever doctor still reports after the partial edits.
_OVERRAN_REPAIR = (
    "Your previous turn was stopped at its wall-clock budget; continue from where you "
    "were — the errors below are what is still red."
)


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
    #: The CLI session id to resume for the story's backbone turns, threaded in from a
    #: prior stage's turn across a `handoff()` boundary. Empty starts a fresh chain.
    session_id: str = ""

    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Grounding-gate failures before the flow fails. `ClassVar` because the YAML exposed no
    #: var for it — the literal `"3"` on `guard_documentation` is the whole budget.
    MAX_REWORKS: ClassVar[int] = 3

    #: Reviewer revisions before the flow fails, counted on their own. See `_rework`
    #: for the run that forced the split.
    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    #: Repair laps that ride one session chain before it is started over. A chain is worth
    #: keeping because lap N+1 already knows what lap N edited and why; past a handful of
    #: laps that value is mostly compaction summary, and a conversation that has been
    #: wrong four times running is a worse starting point than an empty one.
    MAX_CHAIN_LAPS: ClassVar[int] = 4

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    @property
    def _chain(self) -> str:
        """The session chain `repair` runs on, keyed per story.

        Per story rather than per run: a run documents several stories, and a chain they
        shared would open story two's repair on story one's diff — the failure the chain
        exists to avoid, inverted.
        """
        return f"docs-repair:{self.ctx.story_slug}"

    def _story_chain(self) -> str:
        """The backbone conversation this story's primary turn runs on.

        An incoming session id (threaded from a prior stage across a handoff boundary) is
        resumed directly; otherwise a fresh per-story chain is named and the CLI mints one
        the first time it is used. Distinct from `_chain`: that names the narrower,
        intentionally-isolated repair loop, and stays untouched by this one.
        """
        return self.session_id or f"story:{self.ctx.story_slug}"

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's repair chain with it.

        Every terminal goes through here so no exit can forget: a chain left behind is a
        conversation about a book as it was, waiting for the next entry to resume it. The
        backbone chain is the exception: `result.session_id` is stamped with whatever id it
        resolved to, so the parent can thread it into the next stage.
        """
        self.reset_session(self._chain)
        result.session_id = self._require_engine().session_id(self._story_chain())
        return Done(result)

    #: The two budgets, split because the grounding gate and the reviewer fail for
    #: unrelated reasons — see `_rework`. Which one a story spent is the whole point of
    #: keeping them apart, and it is invisible unless both are labelled.
    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("rework", "review_rework")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on, what each gate
        last decided, and whether the pass that decided it bought anything.

        A verdict labels the spans opened *after* it — the author turn a `revise` forced,
        not the review turn that said the word. That is the useful direction, and the same
        one `Qa.state_labels` documents: it lets a query attribute the cost of a rework to
        the verdict that caused it. It is also why `_rework` carries the progress forward
        rather than dropping it at the transition — `groom profile` aggregates agent-turn
        spans only, and `verify` spends no turn, so a gate verdict is visible exactly
        because the next author turn inherits it.
        """
        base = self.labels() | counter_labels(params, "docs", self.BUDGET_LABELS)
        progress = params.get("progress")
        if not isinstance(progress, DocsProgress):
            return base
        carried = progress.model_dump()
        return (
            base
            | counter_labels(carried, "docs", DocsProgress.COUNT_LABELS)
            | verdict_labels(carried, "docs", DocsProgress.VERDICT_LABELS)
        )

    def start(self) -> Continue | Done:
        """Decide whether there is a book to document into, and how the diff can be read.

        `decide_documentation_story` + `resolve_documentation_context` +
        `detect_documentation_okf` + `decide_documentation_okf` +
        `classify_documentation_context`. Four of the five are deterministic and the fifth is
        a guard on `setup`'s own output, so they are one state.

        The three OKF arms are genuinely distinct: `no` ends the flow successfully — most
        repos the coder runs against are not managed by an OKF graph and there is nothing to
        document into — while `invalid` fails it, because a graph that is configured and will
        not load is a broken repo rather than an unmanaged one.
        """
        # Whatever is left of an earlier pass's repair conversation describes a book and a
        # diff that have both moved since. Entry is the one place that is knowable.
        self.reset_session(self._chain)
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
        # The grounding worklist, before the author turn rather than after it. The gate
        # computes the same join from the same packet; paying for it once here is what
        # keeps the author from re-deriving it by hand, which it does badly and at length.
        obligations = self._obligations(classification)
        return Continue(
            okf,
            self.document,
            obligations=tuple(obligations.refs),
            delta_refs=tuple(obligations.refs),
        )

    def document(
        self,
        rework: int = 0,
        review_rework: int = 0,
        gate_notes: str = "",
        review_notes: str = "",
        progress: DocsProgress | None = None,
        obligations: tuple[str, ...] = (),
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
    ) -> Continue | Await | Done:
        """Write the story into the book — the one agent turn this flow spends per pass.

        `document_story` + `decide_documentation_result`. `not_required` is a real answer and
        proceeds to the gate exactly like `documented` does, because "this story changed
        nothing the book describes" is a claim the grounding gate can check.

        A blank status taking the YAML's `default:` arm still fails the flow: an author that
        did not speak has not documented anything, and there is no rework brief to hand it.
        `blocked` is the opposite case and no longer fails — the author *did* speak, and what
        it said is that the book cannot be made true of this code. It comes back as a
        `blocked` `DocsResult` for the caller to place; see `Coder.blocked_docs` for why
        that is one story's finding rather than the whole run's.

        The two notes parameters carry the previous pass's gate and review findings, and are
        threaded rather than reset, because under the YAML both were vars that persisted
        across the loop — a second gate failure still shows the author what the reviewer said
        the first time.

        `progress` is threaded the same way and read by nothing but `state_labels`. It is
        optional rather than defaulted to an instance for two reasons: a shared mutable
        default is a hazard, and an added *optional* parameter is what keeps an in-flight
        checkpoint resumable — `coerce_params` raises on a parameter it does not know, so a
        state that stopped accepting the ones already written would fail every resume.

        `delta_refs` is the *unnarrowed* worklist `start` computed, threaded alongside
        `obligations` rather than folded into it. `obligations` shrinks as the gate closes
        items, which is right for an author being told what is left to do and wrong for a
        reviewer being told what this story is answerable for: a scope that shrinks every pass
        would keep re-legalizing the findings it had just ruled out of bounds. This one
        never narrows, and `review` is its only reader.

        This state is the *first pass only*. A gate failure or a reviewer refusal goes to
        `repair`, which edits the nodes the findings cite instead of re-authoring the book.
        """
        self.logger.info("documenting %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn("document-story", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=DocumentationResult,
            # medium: folding a known change into an existing graph, against a schema and a
            # gate that will check the result. Not a discovery task.
            power="medium",
            session=self._story_chain(),
            add_dirs=self._dirs(),
            args=turn.args | self._author_args(gate_notes, review_notes, obligations),
        )
        return self._authored(
            result,
            rework=rework,
            review_rework=review_rework,
            gate_notes=gate_notes,
            review_notes=review_notes,
            progress=progress,
            delta_refs=delta_refs,
            consulted=consulted,
        )

    def repair(
        self,
        rework: int = 0,
        review_rework: int = 0,
        gate_notes: str = "",
        review_notes: str = "",
        progress: DocsProgress | None = None,
        obligations: tuple[str, ...] = (),
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
    ) -> Continue | Await | Done:
        """Edit the nodes the findings cite, and leave every other node alone.

        Every pass after the first used to re-enter `document`, whose brief is "write this
        story into the book". Handed that instruction plus a finding against one bullet, the
        author revisits nodes nobody complained about — so the `power="high"` reviewer meets a
        changed book each round and, correctly, finds a different real defect in it. That is
        the loop `document-story` averaged 4.5 turns on. Bounding the reviewer's scope (its
        own prompt) only helps if the artifact under review stops moving underneath it, which
        is what this state is for.

        Same signature, same result, same gate as `document`: only the instruction and the
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
        can eat an hour. The cut is survivable for the same reason the QA lane's is: the
        deliverable is the book on disk, not the reply, so `retries=0` and the gate below
        re-runs doctor over whatever landed. The chain is what makes it cheap — the next lap
        opens in the same session, prefixed with `_OVERRAN_REPAIR`.
        """
        self.logger.info("repairing the documentation for %s", self.ctx.story_slug,
                         extra={"activity": True})
        progress = progress or DocsProgress()
        laps = progress.chain_laps
        if laps >= self.MAX_CHAIN_LAPS or progress.gate_progress_verdict == "stalled":
            self.reset_session(self._chain)
            laps = 0
        progress = progress.model_copy(update={"chain_laps": laps + 1})
        overran = ""
        try:
            turn = roles.turn("repair-documentation", self.repo_dir, self.library_dirs)
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
                add_dirs=self._dirs(),
                args=turn.args | self._author_args(gate_notes, review_notes, obligations),
                session=self._chain,
            )
        except AgentTimeout:
            self.logger.info(
                "the documentation repair turn was stopped at its budget — gating what it "
                "wrote",
                extra={"activity": True},
            )
            overran = _OVERRAN_REPAIR
            # Not a claim about the book: the nodes this pass touched are unknown, and the
            # ones every earlier pass named are carried in `authored_nodes` regardless. The
            # gate reads the graph, not this.
            result = DocumentationResult(status="documented", notes=_OVERRAN_REPAIR)
        return self._authored(
            result,
            overran=overran,
            rework=rework,
            review_rework=review_rework,
            gate_notes=gate_notes,
            review_notes=review_notes,
            progress=progress,
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
            consulted=consulted,
        )

    def _author_args(
        self, gate_notes: str, review_notes: str, obligations: tuple[str, ...]
    ) -> dict[str, object]:
        """The brief `document` and `repair` share — same inputs, different instruction."""
        classification = self.output(classify_documentation_context)
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "docs_path": self.docs_path,
            "features_root": self._features_root,
            "epic_path": self._epic_path,
            "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
            "context_mode": classification.mode,
            "context_notes": classification.notes,
            "gate_notes": _prompt_note(gate_notes),
            "review_notes": _prompt_note(review_notes),
            "obligations": list(obligations),
        }

    def _authored(
        self,
        result: DocumentationResult,
        *,
        rework: int,
        review_rework: int,
        gate_notes: str,
        review_notes: str,
        progress: DocsProgress | None,
        delta_refs: tuple[str, ...],
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
        overran: str = "",
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
        # `unfixable` or `invalid` said the same thing, and the raise below would otherwise
        # kill the run over which synonym it reached for.
        if result.blocked:
            self.logger.info(
                "documentation author blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            return self._blocked(
                result.notes,
                consulted=consulted,
                rework=rework,
                gate_notes=gate_notes,
                progress=progress,
                delta_refs=delta_refs,
                authored_nodes=authored_nodes,
            )
        if result.status not in {"documented", "not_required"}:
            raise WorkflowFailed(
                f"documentation author reported {result.status or 'nothing'}: {result.notes}"
            )
        return Continue(
            result,
            self.verify,
            author=result,
            rework=rework,
            review_rework=review_rework,
            gate_notes=gate_notes,
            review_notes=review_notes,
            progress=progress,
            delta_refs=delta_refs,
            authored_nodes=tuple(dict.fromkeys((*authored_nodes, *result.nodes))),
            consulted=consulted,
            overran=overran,
        )

    def verify(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
        review_rework: int = 0,
        progress: DocsProgress | None = None,
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
        overran: str = "",
    ) -> Continue | Await | Done:
        """Check the claim against the diff before any reviewer reads a word of it.

        `decide_documentation_context_mode` + `build_documentation_context` +
        `validate_documentation_context` + `verify_story_documentation` +
        `decide_documentation_gate`.

        In `local` mode the diff is mapped onto the graph deterministically and the gate
        demands *direct* grounding for every changed production unit. In `semantic` mode
        there is no worktree to diff against, so the packet is skipped and doctor plus the
        review turn is the authority. A blank gate status takes the YAML's `default:` arm,
        which is the rework guard — nothing but an explicit pass reaches the reviewer.
        """
        classification = self.output(classify_documentation_context)
        build_status = ""
        validate_status = ""
        if classification.mode == "local":
            build = self.call(
                build_okf_context,
                self.ctx.spec_dir,
                self.ctx.story_path,
                self._features_root,
                tuple(classification.source_roots),
                "HEAD",
                "WORKTREE",
                self.docs_path,
                preexisting=tuple(self.preexisting),
            )
            build_status = build.status
            validate_status = self.call(
                validate_okf_context, self.ctx.spec_dir, build.status, self.docs_path
            ).status
        elif classification.mode != "semantic":
            raise WorkflowFailed(
                f"documentation context mode {classification.mode!r} is not one this flow "
                "knows how to gate."
            )

        gate = self.call(
            verify_story_documentation,
            self.docs_path,
            self.ctx.spec_dir,
            author.status,
            build_status,
            validate_status,
            classification.mode,
            # Every node any pass named, not only this one's — see `_authored`. The `or`
            # is for a checkpoint written before this parameter existed, whose resume
            # arrives here with nothing accumulated.
            authored_nodes or tuple(author.nodes),
            preexisting=tuple(self.preexisting),
        )
        progress = (progress or DocsProgress()).after_gate(gate)
        if gate.status == "passed":
            return Continue(
                gate,
                self.review,
                author=author,
                rework=rework,
                review_rework=review_rework,
                gate_notes=gate.notes,
                review_notes=review_notes,
                progress=progress,
                delta_refs=delta_refs,
                authored_nodes=authored_nodes,
                consulted=consulted,
            )
        # No escape hatch for a shrinking failure set. The gate used to waive the budget
        # while `gate_progress_verdict == "reduced"`, which is exactly the shape a batched
        # worklist produces — twelve errors closed per lap out of a hundred and twenty,
        # forever. The repair turn now gets every affected error at once and iterates
        # doctor itself, so a lap that does not converge is a lap that is not going to —
        # which is a block, not a failure: `_blocked` below, the same arm `review`'s own
        # convergence exhaustion takes a few lines down. A workflow does not give up.
        if rework >= self.MAX_REWORKS:
            return self._blocked(
                (
                    f"documentation did not converge in {self.MAX_REWORKS + 1} grounding "
                    f"passes ({progress.gate_progress_verdict}): {gate.notes or review_notes}"
                ),
                consulted=consulted,
                rework=rework,
                gate_notes=f"{overran}\n\n{gate.notes}".strip() if overran else gate.notes,
                progress=progress,
                delta_refs=delta_refs,
                authored_nodes=authored_nodes,
            )
        # The `G:` identities are the still-ungrounded references, in the inventory's own
        # spelling — the same worklist `start` computed, minus what this pass closed.
        # `overran` is set when the turn that just ran was cut at its budget rather than
        # finishing. The findings below are still the findings — doctor read the book on
        # disk — but the next turn has to be told that its own worklist is half-applied, or
        # it reads the repeat as its edits having failed and starts over.
        return self._rework(
            gate,
            rework + 1,
            review_rework,
            f"{overran}\n\n{gate.notes}".strip() if overran else gate.notes,
            review_notes,
            progress,
            obligations=tuple(
                failure[2:] for failure in gate.failures if failure.startswith("G:")
            ),
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
            consulted=consulted,
        )

    def review(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
        review_rework: int = 0,
        progress: DocsProgress | None = None,
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
    ) -> Continue | Await | Done:
        """An independent read of what was written, downstream of a gate it cannot bypass.

        `review_story_documentation` + `decide_documentation_review`. `blocked` ends the
        flow — the reviewer is saying the story cannot be documented as it stands, which no
        number of rework passes will change — but it ends it with a verdict rather than a
        failure, for the reason `document` gives. `revise`, and a blank taking the YAML's
        `default:`, spends a rework instead.

        **Spending the last rework is the same answer, not a worse one.** A reviewer still
        saying `revise` on the final pass is a reviewer saying the book cannot be made true
        of this code within this budget, which is what `blocked` means; raising instead
        killed the *run*. Returning `blocked` lets `Coder.blocked_docs` contain the finding
        to this story, including when a post-QA mutation made the final recheck mandatory.
        """
        turn = roles.turn("review-story-documentation", self.repo_dir, self.library_dirs)
        result = self.agent(
            turn.prompt,
            returns=DocumentationReview,
            # high: judging whether prose describes the system as built is the harder half
            # of documenting it.
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "features_root": self._features_root,
                "epic_path": self._epic_path,
                "author_status": author.status,
                "author_notes": author.notes,
                "gate_notes": gate_notes,
                "review_notes": review_notes,
                "obligations": list(delta_refs),
            },
        )
        if result.status == "approved":
            self.logger.info("documentation approved for %s", self.ctx.story_slug)
            return self._ends(
                DocsResult(
                    status="passed",
                    notes=result.notes,
                    authored_nodes=list(authored_nodes),
                )
            )
        if result.blocked:
            self.logger.info(
                "documentation review blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            return self._blocked(
                result.notes,
                # A reviewer that refused still names what it read as wrong. Those findings
                # are what an operator needs to rule on, and without them the gate says only
                # that documentation is impossible, not which contradiction made it so.
                findings=result.actionable,
                consulted=consulted,
                rework=rework,
                gate_notes=gate_notes,
                progress=progress,
                delta_refs=delta_refs,
                authored_nodes=authored_nodes,
            )
        finding_problems = _review_finding_problems(result)
        if result.status == "revise" and finding_problems:
            raise WorkflowFailed(
                "documentation reviewer requested revisions with invalid structured findings: "
                + "; ".join(finding_problems)
            )
        # After the structural check, so a malformed `revise` still fails on its findings
        # rather than being scored on them.
        progress = (progress or DocsProgress()).after_review(result)
        notes = _review_notes(result)
        if review_rework >= self.MAX_REVIEW_REWORKS:
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
                    f"({progress.review_progress_verdict}): "
                    f"{notes or gate_notes or 'no notes'}"
                ),
                consulted=consulted,
                rework=rework,
                gate_notes=gate_notes,
                progress=progress,
                delta_refs=delta_refs,
                authored_nodes=authored_nodes,
            )
        return self._rework(
            result, rework, review_rework + 1, gate_notes, notes, progress,
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
            consulted=consulted,
        )

    def _rework(
        self,
        result: object,
        rework: int,
        review_rework: int,
        gate_notes: str,
        review_notes: str,
        progress: DocsProgress | None = None,
        obligations: tuple[str, ...] = (),
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        consulted: bool = False,
    ) -> Continue:
        """`guard_documentation`'s other half: send the author back with what it must fix.

        Not a state — the routing half of a branch, called from the two states that can
        decide the documentation is not good enough. `_`-prefixed so state discovery does not
        pick it up.

        **The two counters are deliberately separate**, which the YAML's single
        `documentation_rework_count` was not. The grounding gate is deterministic — it names
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
        return Continue(
            result,
            self.repair,
            rework=rework,
            review_rework=review_rework,
            gate_notes=gate_notes,
            review_notes=review_notes,
            progress=progress,
            obligations=obligations,
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
            consulted=consulted,
        )

    # ── the author gate ───────────────────────────────────────────────────────────────

    def _blocked(
        self,
        notes: str,
        *,
        consulted: bool,
        rework: int,
        gate_notes: str,
        progress: DocsProgress | None,
        delta_refs: tuple[str, ...],
        authored_nodes: tuple[str, ...],
        findings: Sequence[Finding] = (),
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

        One consult per flow. `consulted` is threaded through every state rather than kept
        beside the run, because a second block after a guided lap is the loop this guard
        exists to stop: the review budget is spent by then, so the next review would block
        again immediately and the pair would cycle forever.

        `human`/`operator` mode still parks — someone asked to be asked.

        `findings` reaches the gate body but deliberately not `carried`: it is evidence for
        whoever reads the escalation, and putting it in the checkpoint would widen every
        downstream state's parameters — which *are* the checkpoint — for a value none of them
        read.
        """
        if consulted:
            return self._ends(DocsResult(status="blocked", notes=notes))
        carried: dict[str, Any] = {
            "notes": notes,
            "rework": rework,
            "gate_notes": gate_notes,
            "progress": progress,
            "delta_refs": delta_refs,
            "authored_nodes": authored_nodes,
        }
        if self.operator_mode in {"human", "operator"}:
            gate = escalation(
                self,
                block_kind="docs",
                where=f"the docs stage, after {rework} rework pass(es)",
                notes=notes,
                # One consult per flow (`consulted` returns above), so a docs block is
                # always this story's first documentation escalation.
                number=1,
                findings=findings,
            )
            return Await(self._context, gate.body, self.read_author, **carried)
        return Continue(None, self.resolve_author, **carried)

    def resolve_author(
        self,
        notes: str = "",
        rework: int = 0,
        gate_notes: str = "",
        progress: DocsProgress | None = None,
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
    ) -> Continue | Done:
        """Stand in for the author who wrote the specs, and ratify what the book contradicts.

        The same resolver `qa`, `dev` and `review` reach, on `block_kind="docs"`, and this
        is the lane whose answering arm was never removed — the port kept it because a docs
        block is so often a question the documents themselves already answer. What the
        resolver may answer *from* is now written down (`shared/resolution.py`): a decision
        record, a repo rule, an installed skill, an acceptance criterion. Having done so it
        amends the authored documents, so the decision is the product's and not this run's.

        An escalation ends the flow blocked rather than waiting, for the reason
        `Qa.resolve_operator` gives: the story drain is single-threaded, so a parked story
        parks every epic behind it. The block is not silent: it surfaces as the run's own
        failure, carrying its reason, which is what an operator polls for.
        """
        self.logger.info("resolving the documentation block", extra={"activity": True})
        result = self.agent(
            "prompts/resolve-operator.md",
            returns=OperatorResolution,
            # smart, and unbounded: the same reasoning `qa` documents — standing in for the
            # accountable party, with full tool access, on the flow's costliest decision.
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=self._dirs(),
            args=resolver_args(
                self, block_kind="docs", notes=notes, docs_path=self.docs_path
            ),
        )
        if not answered(self, result, "docs"):
            self.logger.info("the documentation resolver escalated — blocking the story")
            return self._ends(DocsResult(status="blocked", notes=notes))
        return Continue(
            result,
            self.read_author,
            notes=notes,
            rework=rework,
            gate_notes=gate_notes,
            progress=progress,
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
        )

    def read_author(
        self,
        notes: str = "",
        rework: int = 0,
        gate_notes: str = "",
        progress: DocsProgress | None = None,
        delta_refs: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
    ) -> Continue | Done:
        """Take the ratified decision off `context.md` and spend one repair lap on it.

        An `epic`-scoped answer is not something this flow can act on — it says the epic's
        premise was wrong, which no edit to one story's documentation reaches — so it comes
        back as the block's verdict, carrying the answer as the notes `Coder.blocked_docs`
        puts into the failure.

        `review_rework` resets. The reviewer's budget was spent arguing about a question
        that had no ratified answer; now there is one, and re-entering with nothing left to
        spend would block again on the next pass without the author ever seeing it. The
        budget is bounded either way, because `consulted` makes this the only reset.
        """
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("the author scoped the documentation block to the epic")
            return self._ends(DocsResult(status="blocked", notes=answer.content or notes))
        brief = "\n".join(
            part for part in (f"Ratified by the author: {answer.content}".strip(), notes) if part
        )
        return self._rework(
            answer,
            rework,
            0,
            gate_notes,
            brief,
            progress,
            delta_refs=delta_refs,
            authored_nodes=authored_nodes,
            consulted=True,
        )

    @property
    def _context(self) -> Path:
        """The file an `Await` writes its questions into: `<story-folder>/context.md`."""
        return paths.story_context_path(self.ctx.story_path)

    def _obligations(self, classification: ContextClassification) -> DocumentationObligations:
        """Build the diff packet and read the grounding worklist off it, before authoring.

        `local` mode only: `semantic` mode has no worktree to diff, and the node says so
        rather than returning an empty worklist that would read as "nothing to ground".
        The packet is rebuilt in `verify` against the tree the author left behind — this
        one is the *before* picture and is deliberately not reused as the gate's input.
        """
        if classification.mode != "local":
            return self.call(
                documentation_obligations,
                self.docs_path,
                self.ctx.spec_dir,
                classification.mode,
                "",
                preexisting=tuple(self.preexisting),
            )
        build = self.call(
            build_okf_context,
            self.ctx.spec_dir,
            self.ctx.story_path,
            self._features_root,
            tuple(classification.source_roots),
            "HEAD",
            "WORKTREE",
            self.docs_path,
            preexisting=tuple(self.preexisting),
        )
        return self.call(
            documentation_obligations,
            self.docs_path,
            self.ctx.spec_dir,
            classification.mode,
            build.status,
            preexisting=tuple(self.preexisting),
        )

    @property
    def _features_root(self) -> str:
        """Where the OKF feature docs live, as the detector resolved it."""
        return self.output(detect_okf_docs).features_root

    @property
    def _epic_path(self) -> str:
        """The parent epic whose user journeys this story advances."""
        root = Path(find_docs_root(self.docs_path, self.repo_dir))
        return f"{paths.epic_dir_rel(root, self.ctx.story_epic)}/epic.md"

    def _dirs(self) -> list[str]:
        """Every directory this run's agent turns may read."""
        return list(self.output(resolve_workspace_dirs).dirs)


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
