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

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed
from workhorse.scriptutil import find_docs_root
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
    DocsProgress,
    DocsResult,
    DocumentationFinding,
    DocumentationResult,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels, verdict_labels


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

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        return self.call(prepare_story, self.docs_path, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on — the YAML's `labels:` block."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

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
        self,
        rework: int = 0,
        review_rework: int = 0,
        gate_notes: str = "",
        review_notes: str = "",
        progress: DocsProgress | None = None,
    ) -> Continue | Done:
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
                "epic_path": self._epic_path,
                "context_mode": classification.mode,
                "context_notes": classification.notes,
                "gate_notes": gate_notes,
                "review_notes": review_notes,
            },
        )
        if result.status == "blocked":
            self.logger.info(
                "documentation author blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            return Done(DocsResult(status="blocked", notes=result.notes))
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
        )

    def verify(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
        review_rework: int = 0,
        progress: DocsProgress | None = None,
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
            tuple(author.nodes),
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
            )
        if rework >= self.MAX_REWORKS:
            raise WorkflowFailed(
                f"documentation did not converge in {self.MAX_REWORKS + 1} grounding "
                f"passes ({progress.gate_progress_verdict}): {gate.notes or review_notes}"
            )
        return self._rework(
            gate, rework + 1, review_rework, gate.notes, review_notes, progress
        )

    def review(
        self,
        author: DocumentationResult,
        rework: int,
        gate_notes: str,
        review_notes: str,
        review_rework: int = 0,
        progress: DocsProgress | None = None,
    ) -> Continue | Done:
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
                "epic_path": self._epic_path,
                "author_status": author.status,
                "author_notes": author.notes,
                "gate_notes": gate_notes,
                "review_notes": review_notes,
            },
        )
        if result.status == "approved":
            self.logger.info("documentation approved for %s", self.ctx.story_slug)
            return Done(DocsResult(status="passed", notes=result.notes))
        if result.status == "blocked":
            self.logger.info(
                "documentation review blocked on %s: %s", self.ctx.story_slug, result.notes
            )
            return Done(DocsResult(status="blocked", notes=result.notes))
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
            return Done(
                DocsResult(
                    status="blocked",
                    notes=(
                        f"documentation review did not converge in "
                        f"{self.MAX_REVIEW_REWORKS + 1} passes "
                        f"({progress.review_progress_verdict}): "
                        f"{notes or gate_notes or 'no notes'}"
                    ),
                )
            )
        return self._rework(
            result, rework, review_rework + 1, gate_notes, notes, progress
        )

    def _rework(
        self,
        result: object,
        rework: int,
        review_rework: int,
        gate_notes: str,
        review_notes: str,
        progress: DocsProgress | None = None,
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
        `_guard_plan_validation` / `_guard_plan_review` split fixes.
        """
        return Continue(
            result,
            self.document,
            rework=rework,
            review_rework=review_rework,
            gate_notes=gate_notes,
            review_notes=review_notes,
            progress=progress,
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
    """Why a revision response is not an actionable, stable repair contract."""
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
        elif not finding.id.startswith("D") or not finding.id[1:].isdigit():
            problems.append(f"finding {index} has invalid id {finding.id!r}")
    return problems


def _review_notes(review: DocumentationReview) -> str:
    """The repair brief: structured findings first, summary second."""
    lines = [_format_finding(finding) for finding in review.findings]
    if review.notes:
        lines.append(f"Summary: {review.notes}")
    return "\n".join(lines)


__all__ = ["Docs"]
