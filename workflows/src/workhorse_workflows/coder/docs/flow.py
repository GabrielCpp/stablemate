"""Fold a finished story into the as-built OKF book, and refuse to believe it was — the port
of `coder/workflow.yaml`'s `flows.docs` (22 nodes, lines 2176-2437).

Reached from the main graph at four call sites (`docs`, `final_docs`, `failed_docs` and
`document_fix_item`, the last through the `*docs_flow` anchor inside `flows.fix`), and
standalone as `workhorse run coder docs`::

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
  is the only budget the YAML had.
* **`documentation_failed` was a `type: fail`**, so every arm that reached it raises
  `WorkflowFailed` at the deciding site. What the four call sites' `default: failed` was for
  — a sub-flow that produced no value at all — cannot happen here, and `DocsResult`'s
  default records that.
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
"""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.dev import resolve_impl_context
from workhorse_workflows.coder.shared.docs import (
    classify_documentation_context,
    detect_okf_docs,
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.story import prepare_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.docs import (
    DocsResult,
    DocumentationResult,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths


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


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: Document/gate passes before the flow fails. `ClassVar` because the YAML exposed no
    #: var for it — the literal `"3"` on `guard_documentation` is the whole budget.
    MAX_REWORKS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

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
            return Done(DocsResult(status="not_applicable", notes=okf.reason))
        if okf.has_okf != "yes":
            raise WorkflowFailed(f"OKF documentation is unusable here: {okf.reason}")
        self.call(
            classify_documentation_context, self.docs_path, tuple(impl.qa_source_roots)
        )
        return Continue(okf, self.document)

    def document(
        self, rework: int = 0, gate_notes: str = "", review_notes: str = ""
    ) -> Continue:
        """Write the story into the book — the one agent turn this flow spends per pass.

        `document_story` + `decide_documentation_result`. `not_required` is a real answer and
        proceeds to the gate exactly like `documented` does, because "this story changed
        nothing the book describes" is a claim the grounding gate can check. `blocked`, and a
        blank taking the YAML's `default:` arm, fail the flow: an author that did not speak
        has not documented anything, and there is no rework brief to hand it.

        The two notes parameters carry the previous pass's gate and review findings, and are
        threaded rather than reset, because under the YAML both were vars that persisted
        across the loop — a second gate failure still shows the author what the reviewer said
        the first time.
        """
        self.logger.info("documenting %s", self.ctx.story_slug, extra={"activity": True})
        classification = self.output(classify_documentation_context)
        result = self.agent(
            "prompts/document-story.md",
            returns=DocumentationResult,
            # medium: folding a known change into an existing graph, against a schema and a
            # gate that will check the result. Not a discovery task.
            power="medium",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "story_slug": self.ctx.story_slug,
                "docs_path": self.docs_path,
                "features_root": self._features_root,
                "context_mode": classification.mode,
                "context_notes": classification.notes,
                "gate_notes": gate_notes,
                "review_notes": review_notes,
            },
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
            gate_notes=gate_notes,
            review_notes=review_notes,
        )

    def verify(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
    ) -> Continue:
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
            tuple(author.nodes),
        )
        if gate.status == "passed":
            return Continue(
                gate,
                self.review,
                author=author,
                rework=rework,
                gate_notes=gate.notes,
                review_notes=review_notes,
            )
        return self._guard(gate, rework, gate.notes, review_notes)

    def review(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
    ) -> Continue | Done:
        """An independent read of what was written, downstream of a gate it cannot bypass.

        `review_story_documentation` + `decide_documentation_review`. `blocked` fails the
        flow — the reviewer is saying the story cannot be documented as it stands, which no
        number of rework passes will change. `revise`, and a blank taking the YAML's
        `default:`, spends a rework instead.
        """
        result = self.agent(
            "prompts/review-story-documentation.md",
            returns=DocumentationReview,
            # high: judging whether prose describes the system as built is the harder half
            # of documenting it.
            power="high",
            add_dirs=self._dirs(),
            args={
                "story_path": self.ctx.story_path,
                "spec_dir": self.ctx.spec_dir,
                "docs_path": self.docs_path,
                "features_root": self._features_root,
                "author_status": author.status,
                "author_notes": author.notes,
                "gate_notes": gate_notes,
            },
        )
        if result.status == "approved":
            self.logger.info("documentation approved for %s", self.ctx.story_slug)
            return Done(DocsResult(status="passed", notes=result.notes))
        if result.status == "blocked":
            raise WorkflowFailed(f"documentation review blocked: {result.notes}")
        return self._guard(result, rework, gate_notes, result.notes)

    def _guard(
        self, result: object, rework: int, gate_notes: str, review_notes: str
    ) -> Continue:
        """`guard_documentation`: another document pass, or fail the flow.

        Not a state — the routing half of a branch, called from the two states that can
        decide the documentation is not good enough. `_`-prefixed so state discovery does not
        pick it up.
        """
        if rework >= self.MAX_REWORKS:
            raise WorkflowFailed(
                f"documentation did not converge in {self.MAX_REWORKS + 1} passes: "
                f"{review_notes or gate_notes}"
            )
        return Continue(
            result,
            self.document,
            rework=rework + 1,
            gate_notes=gate_notes,
            review_notes=review_notes,
        )

    @property
    def _features_root(self) -> str:
        """Where the OKF feature docs live, as the detector resolved it."""
        return self.output(detect_okf_docs).features_root

    def _dirs(self) -> list[str]:
        """Every directory this run's agent turns may read."""
        return list(self.output(resolve_workspace_dirs).dirs)


__all__ = ["Docs"]
