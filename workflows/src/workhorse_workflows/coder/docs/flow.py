"""Fold a finished story into the as-built OKF book, and refuse to believe it was."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import AgentTimeout, Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.kit import build_worklist, find_docs_root
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.dev import (
    plan_summary,
    read_operator_context,
    resolve_impl_context,
    resolve_story_sources,
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

UNBOUNDED = float("inf")

_OVERRAN_REPAIR = (
    "Your previous turn was stopped at its wall-clock budget; continue from where you "
    "were — the errors below are what is still red."
)


def _overran_brief(gate_notes: str) -> str:
    """Prefix the standing rework brief with the cut, without stacking prefixes."""
    standing = gate_notes.removeprefix(_OVERRAN_REPAIR).strip()
    return f"{_OVERRAN_REPAIR}\n\n{standing}".strip() if standing else _OVERRAN_REPAIR


def _prompt_note(note: str) -> str:
    """Last-resort bound on a brief that would not fit an argv."""
    if len(note) <= MAX_PROMPT_NOTE_CHARS:
        return note
    return (
        note[:MAX_PROMPT_NOTE_CHARS].rstrip()
        + "\n\n... note truncated for the agent prompt; re-run `ostler doctor` yourself for "
        "the rest."
    )


class Docs(Workflow):
    """Document one story against the OKF graph, and gate the claim against the diff."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    target_env: str = "local"
    preexisting: tuple[str, ...] = ()
    operator_mode: str = "auto"

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    MAX_REWORKS: ClassVar[int] = 3

    MAX_REVIEW_REWORKS: ClassVar[int] = 3

    MAX_DOCS_BLOCKS: ClassVar[int] = 3

    MAX_CHAIN_LAPS: ClassVar[int] = 4

    MAX_REPAIR_OVERRUNS: ClassVar[int] = 3

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    @property
    def _chain(self) -> str:
        """The session chain `repair` runs on, keyed per story."""
        return f"docs-repair:{self.ctx.story_slug}"

    def _reset_chains(self) -> None:
        """Drop both chains this flow's turns run on for the current story."""
        self.reset_session(backbone(self))
        self.reset_session(self._chain)

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's repair chain with it."""
        self.reset_session(self._chain)
        return Done(result)

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on, what each gate last decided, and whether the pass that decided it bought anything."""
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
        """Decide whether there is a book to document into, and how the diff can be read."""
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
        if self.workspace_file and self.ctx.story_id:
            sources = self.call(
                resolve_story_sources,
                tuple(impl.dispatch_list),
                self.ctx.story_slug,
                self.ctx.story_id,
                self.docs_path,
            )
            if sources.status != "valid":
                raise WorkflowFailed(
                    "story source provenance could not be resolved: "
                    + "; ".join(sources.errors)
                )
        obligations = self._obligations(classification)
        return Continue(
            okf, self.document, loop=DocsLoop(obligations=tuple(obligations.refs))
        )

    def document(self, loop: DocsLoop) -> Continue | Await | Done:
        """Write the story into the book — the one agent turn this flow spends per pass."""
        self.logger.info("documenting %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "document-story", returns=DocumentationResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="medium",
            session=backbone(self),
            add_dirs=workspace_dirs(self),
            args=turn.args | self._author_args(loop),
        )
        return self._authored(result, loop)

    def repair(self, loop: DocsLoop) -> Continue | Await | Done:
        """Edit the nodes the findings cite, and leave every other node alone."""
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
            turn = roles.turn(self, "repair-documentation", returns=DocumentationResult)
            result = self.agent(
                turn.prompt,
                returns=turn.returns,
                power="low",
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
        """Re-dispatch a repair turn that was cut at its wall-clock budget."""
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
            "story_id": self.ctx.story_id or self.ctx.story_slug,
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
        """The tail both author turns share: the contract on the answer, then the gate."""
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
        """Check the claim against the diff before any reviewer reads a word of it."""
        classification = self.output(classify_documentation_context)
        mode = self._context_mode(classification)
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
            loop.authored_nodes,
            preexisting=tuple(self.preexisting),
        )
        loop = loop.model_copy(update={"progress": loop.progress.after_gate(gate)})
        if gate.status == "passed":
            return Continue(
                gate,
                self.review,
                author=author,
                loop=loop.model_copy(
                    update={"gate_notes": gate.notes, "obligations": ()}
                ),
            )
        notes = gate.notes
        if loop.rework >= self.MAX_REWORKS:
            return self._blocked(
                (
                    f"documentation did not converge in {self.MAX_REWORKS + 1} grounding "
                    f"passes ({loop.progress.gate_progress_verdict}): "
                    f"{gate.notes or loop.review_notes}"
                ),
                loop.model_copy(update={"gate_notes": notes}),
            )
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
        """An independent read of what was written, downstream of a gate it cannot bypass."""
        turn = roles.turn(self, "review-story-documentation", returns=DocumentationReview)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
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
            return self._blocked(result.notes, loop, findings=result.actionable)
        finding_problems = _review_finding_problems(result)
        if finding_problems:
            raise WorkflowFailed(
                "documentation reviewer requested revisions with invalid structured findings: "
                + "; ".join(finding_problems)
            )
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
        """Send the author back with what it must fix."""
        return Continue(result, self.repair, loop=loop)


    def _blocked(
        self, notes: str, loop: DocsLoop, *, findings: Sequence[Finding] = ()
    ) -> Continue | Await | Done:
        """A block ends the flow — but not before the author it belongs to gets a say."""
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
        """Stand in for the author who wrote the specs, and ratify what the book contradicts."""
        self.logger.info("resolving the documentation block", extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
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
        """Take the ratified decision off `context.md` and spend one repair lap on it."""
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
        """Map this story's code diff onto the OKF graph, and write the packet beside it."""
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
            story_sources=(
                self.output(resolve_story_sources).sources
                if self.workspace_file and self.ctx.story_id
                else ()
            ),
        )

    def _context_mode(self, classification: ContextClassification) -> str:
        """Treat an explicit external repository packet as locally verifiable."""
        if (
            self.workspace_file
            and self.ctx.story_id
            and self.output(resolve_story_sources).sources
        ):
            return "local"
        return classification.mode

    def _obligations(self, classification: ContextClassification) -> DocumentationObligations:
        """Build the diff packet and read the grounding worklist off it, before authoring."""
        mode = self._context_mode(classification)
        build_status = ""
        packet = None
        if mode == "local":
            packet = self._okf_packet(classification)
            build_status = packet.status
        obligations = self.call(
            documentation_obligations,
            self.docs_path,
            self.ctx.spec_dir,
            mode,
            build_status,
            preexisting=tuple(self.preexisting),
        )
        if packet is not None and packet.ostler:
            paths = sorted({
                str(unit.get("path", ""))
                for unit in (packet.ostler.get("changedUnits") or [])
                if isinstance(unit, dict) and unit.get("path")
            })
            if paths:
                try:
                    docs_root = Path(find_docs_root(self.docs_path, self.repo_dir))
                    scoped = build_worklist(
                        docs_root,
                        Path(features_root(self)),
                        "",
                        paths=paths,
                    )
                except (OSError, ValueError, RuntimeError) as exc:
                    self.logger.info("scoped worklist builder skipped: %s", exc)
                else:
                    self.logger.info(
                        "%d changed path(s): %d missing unit(s) per the worklist builder",
                        len(paths), len(scoped.missing),
                        extra={"activity": True},
                    )
        return obligations

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
    return problems


def _review_notes(review: DocumentationReview) -> str:
    """The repair brief: structured findings first, summary second."""
    lines = [_format_finding(finding) for finding in review.findings]
    if review.notes:
        lines.append(f"Summary: {review.notes}")
    return "\n".join(lines)


__all__ = ["Docs"]
