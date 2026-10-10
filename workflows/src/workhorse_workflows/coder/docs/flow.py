"""One docs owner folds a finished story into the as-built OKF book through its subagents, and the run checks it."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared.plan import plan_summary, resolve_impl_context
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.provenance import resolve_story_sources
from workhorse_workflows.coder.shared.docs import (
    MAX_PROMPT_NOTE_CHARS,
    classify_documentation_context,
    detect_okf_docs,
    documentation_obligations,
    features_root,
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
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
    DocsResult,
    DocumentationObligations,
    DocumentationResult,
)
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels


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

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks", "number")

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        ctx = self.call(prepare_story, self.docs_path, self.story, self.epic)
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "docs", self.BUDGET_LABELS)

    @property
    def _chain(self) -> str:
        """The docs owner's own session, keyed per story."""
        return f"docs:{self.ctx.story_slug}"

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's docs session with it."""
        self.reset_session(self._chain)
        return Done(result)

    def start(self) -> Continue | Done:
        """Decide whether there is a book to document into, and how the diff can be read."""
        self.reset_session(self._chain)
        if not self.ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r}. The story could not be resolved, so "
                "there is nothing to document."
            )
        impl = self.call(
            resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path
        )
        okf = self.call(detect_okf_docs, self.docs_path)
        if okf.has_okf == "no":
            self.logger.info("no OKF docs here, so there is nothing to document")
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
        return Continue(okf, self.work, obligations=tuple(obligations.refs))

    def work(
        self,
        obligations: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        report: str = "",
        operator_context: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the owner turn: its subagents write the story into the book, review it and fix it."""
        self.logger.info("documenting %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "document-story", returns=DocumentationResult)
        result: DocumentationResult = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("docs"),
            session=self._chain,
            add_dirs=workspace_dirs(self),
            args=turn.args
            | self._brief()
            | {
                "report": _prompt_note(report),
                "operator_context": operator_context,
                "obligations": list(obligations),
            },
        )
        carried = {"obligations": obligations, "authored_nodes": authored_nodes}
        if result.blocked:
            return self._block(result, result.notes, "the docs turn", blocks, carried)
        return Continue(
            result,
            self.check,
            author=result,
            obligations=obligations,
            authored_nodes=tuple(dict.fromkeys((*authored_nodes, *result.nodes))),
            laps=laps,
            blocks=blocks,
        )

    def _brief(self) -> dict[str, object]:
        """What the owner reads before it writes a word: the story, the book and the diff's shape."""
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
        }

    def check(
        self,
        author: DocumentationResult,
        obligations: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await | Done:
        """Check the book against the diff, and send what failed back to the owner."""
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
            authored_nodes,
            preexisting=tuple(self.preexisting),
        )
        if gate.status == "passed":
            return Continue(
                gate, self.finish, notes=gate.notes or author.notes, authored_nodes=authored_nodes
            )
        carried = {"obligations": obligations, "authored_nodes": authored_nodes}
        if laps >= MAX_LAPS:
            notes = f"{gate.notes}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(gate, notes, "the checks", blocks, carried)
        return Continue(
            gate,
            self.work,
            report=gate.notes,
            obligations=tuple(f[2:] for f in gate.failures if f.startswith("G:")),
            authored_nodes=authored_nodes,
            laps=laps + 1,
            blocks=blocks,
        )

    def finish(self, notes: str = "", authored_nodes: tuple[str, ...] = ()) -> Done:
        """Hand back the nodes the owner wrote, now that the gate holds."""
        self.logger.info("documentation passed for %s", self.ctx.story_slug)
        return self._ends(
            DocsResult(status="passed", notes=notes, authored_nodes=list(authored_nodes))
        )

    def _block(
        self, result: object, notes: str, where: str, blocks: int, carried: dict[str, Any]
    ) -> Continue | Await:
        self.logger.info("documentation blocked on %s: %s", self.ctx.story_slug, notes)
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks, carried)
        return Continue(
            result, self.resolve, notes=notes, where=where, blocks=blocks, **carried
        )

    def _ask(
        self,
        notes: str,
        where: str,
        blocks: int,
        carried: dict[str, Any],
        result: OperatorResolution | None = None,
    ) -> Await:
        gate = escalation(
            self,
            block_kind="docs",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
        )
        return Await(
            context_path(self),
            gate.body,
            self.read_operator,
            notes=notes,
            blocks=blocks + 1,
            **carried,
        )

    def resolve(
        self,
        notes: str,
        where: str,
        blocks: int = 0,
        obligations: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
    ) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=workspace_dirs(self),
            args=resolver_args(self, block_kind="docs", notes=notes, docs_path=self.docs_path),
        )
        carried = {"obligations": obligations, "authored_nodes": authored_nodes}
        if answered(self, result, "docs"):
            return Continue(
                result, self.read_operator, notes=notes, blocks=blocks + 1, **carried
            )
        return self._ask(notes, where, blocks, carried, result)

    def read_operator(
        self,
        notes: str = "",
        blocks: int = 0,
        obligations: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
    ) -> Continue | Done:
        """Resume the owner's session with the answer in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the documentation block to the epic")
            return self._ends(DocsResult(status="blocked", notes=answer.content or notes))
        return Continue(
            answer,
            self.work,
            operator_context=answer.content,
            obligations=obligations,
            authored_nodes=authored_nodes,
            blocks=blocks,
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
        if mode == "local":
            build_status = self._okf_packet(classification).status
        return self.call(
            documentation_obligations,
            self.docs_path,
            self.ctx.spec_dir,
            mode,
            build_status,
            preexisting=tuple(self.preexisting),
        )

    @property
    def _epic_path(self) -> str:
        """The parent epic whose user journeys this story advances."""
        root = Path(find_docs_root(self.docs_path, self.repo_dir))
        return f"{paths.epic_dir_rel(root, self.ctx.story_epic)}/epic.md"


__all__ = ["Docs"]
