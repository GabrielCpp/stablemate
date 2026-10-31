"""One docs owner folds a finished story into the as-built OKF book through its subagents, and the run checks it."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared.plan import plan_summary, resolve_impl_context
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.qa.nodes import compile_story_plan
from workhorse_workflows.coder.shared.failed import failed_scenario_ids, failed_scenarios_arg
from workhorse_workflows.coder.shared.provenance import resolve_story_sources
from workhorse_workflows.coder.shared.compilation import compile_gaps
from workhorse_workflows.coder.shared.docs import (
    EXERCISE_LABEL,
    MAX_PROMPT_NOTE_CHARS,
    classify_documentation_context,
    detect_okf_docs,
    documentation_obligations,
    exercise_text,
    services_root,
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
from workhorse_workflows.coder.shared.okf import TRUNK, build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.stack import (
    ensure_stack,
    release_copy,
    run_qa_plan,
    stack_target,
)
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.docs import (
    ContextClassification,
    DocsResult,
    DocumentationGate,
    DocumentationObligations,
    DocumentationResult,
    SpecResult,
)
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.qa.runner import copy_lease
from workhorse_workflows.kit.qa.support import QA_PLAN_FILE
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
    epic: str = ""
    target_env: str = "local"
    preexisting: tuple[str, ...] = ()
    operator_mode: str = "auto"
    phase: Literal["spec", "build"] = "build"
    spec_nodes: tuple[str, ...] = ()

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks", "number")

    def setup(self) -> StoryPaths:
        """Resolve the workspace to directories and the story to its id and paths."""
        self.call(resolve_workspace_dirs)
        self.call(detect_okf_docs)
        return self.call(prepare_story, self.story, self.epic)

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "docs", self.BUDGET_LABELS)

    @property
    def _chain(self) -> str:
        """The docs owner's own session, keyed per story."""
        prefix = "docs-spec" if self.phase == "spec" else "docs"
        return f"{prefix}:{self.ctx.story_slug}"

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's docs session with it."""
        self.reset_session(self._chain)
        return Done(result)

    def start(self) -> Continue | Done:
        """Decide whether there is a book to document into, and how the diff can be read."""
        self.reset_session(self._chain)
        okf = self.output(detect_okf_docs)
        if okf.has_okf != "yes":
            raise WorkflowFailed(f"OKF documentation is unusable here: {okf.reason}")
        if not self.ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r}. The story could not be resolved, so "
                "there is nothing to document."
            )
        if self.phase == "spec":
            return Continue(okf, self.work)
        impl = self.call(resolve_impl_context, self.ctx.spec_dir)
        classification = self.call(
            classify_documentation_context, tuple(impl.qa_source_roots)
        )
        if classification.mode == "error":
            raise WorkflowFailed(
                f"the documentation context could not be read: {classification.notes}"
            )
        if self.workspace and self.ctx.story_id:
            sources = self.call(
                resolve_story_sources,
                tuple(impl.dispatch_list),
                self.ctx.story_slug,
                self.ctx.story_id,
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
        exercised: bool = False,
    ) -> Continue | Await:
        """Run the owner turn: its subagents write the story into the book, review it and fix it."""
        spec = self.phase == "spec"
        self.logger.info(
            "specifying %s" if spec else "documenting %s",
            self.ctx.story_slug,
            extra={"activity": True},
        )
        turn = (
            roles.turn(self, "specify-story", returns=SpecResult)
            if spec
            else roles.turn(self, "document-story", returns=DocumentationResult)
        )
        result: DocumentationResult | SpecResult = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("docs"),
            session=self._chain,
            add_dirs=workspace_dirs(self),
            args=turn.args
            | (
                self._spec_brief()
                if spec
                else self._brief() | {"spec_nodes": list(self.spec_nodes)}
            )
            | {
                "report": _prompt_note(report),
                "operator_context": operator_context,
            }
            | ({} if spec else {"obligations": list(obligations)}),
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
            exercised=exercised,
        )

    def _spec_brief(self) -> dict[str, object]:
        """What the spec pass reads before it writes a word: the story and the book, with no diff yet."""
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "docs_root": str(find_docs_root(self.repo_dir)),
            "services_root": services_root(self),
            "epic_path": self._epic_path,
        }

    def _brief(self) -> dict[str, object]:
        """What the owner reads before it writes a word: the story, the book and the diff's shape."""
        classification = self.output(classify_documentation_context)
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "docs_root": str(find_docs_root(self.repo_dir)),
            "services_root": services_root(self),
            "epic_path": self._epic_path,
            "plan_services": self.call(plan_summary, self.ctx.spec_dir).text,
            "context_mode": classification.mode,
            "context_notes": classification.notes,
        }

    def check(
        self,
        author: DocumentationResult | SpecResult,
        obligations: tuple[str, ...] = (),
        authored_nodes: tuple[str, ...] = (),
        laps: int = 0,
        blocks: int = 0,
        exercised: bool = False,
    ) -> Continue | Await | Done:
        """Check the book against the diff, and send what failed back to the owner."""
        mode: Literal["local", "semantic", "error"] = "semantic"
        build_status: Literal["", "passed", "invalid"] = ""
        validate_status: Literal["", "passed", "invalid"] = ""
        if self.phase != "spec":
            classification = self.output(classify_documentation_context)
            mode = self._context_mode(classification)
            if mode == "error":
                raise WorkflowFailed(
                    f"the documentation context could not be read: {classification.notes}"
                )
            if mode == "local":
                build = self._okf_packet(classification)
                build_status = build.status
                validate_status = self.call(
                    validate_okf_context, self.ctx.spec_dir, build.status
                ).status
        gate = self.call(
            verify_story_documentation,
            self.ctx.spec_dir,
            author.status,
            build_status,
            validate_status,
            mode,
            authored_nodes,
            preexisting=tuple(self.preexisting),
        )
        if self.phase != "spec" and mode == "local" and build_status == "passed":
            gate = self._with_compile_gaps(gate, authored_nodes)
            if gate.status == "passed":
                gate = self._with_exercise(gate, exercised)
        if gate.status == "passed":
            return Continue(
                gate, self.finish, notes=gate.notes or author.notes, authored_nodes=authored_nodes
            )
        carried = {"obligations": obligations, "authored_nodes": authored_nodes}
        if any(f.startswith("X:") for f in gate.failures):
            return Continue(
                gate,
                self.work,
                report=gate.notes,
                obligations=obligations,
                authored_nodes=authored_nodes,
                laps=laps,
                blocks=blocks,
                exercised=True,
            )
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
            exercised=exercised,
        )

    def _with_compile_gaps(
        self, gate: DocumentationGate, authored_nodes: tuple[str, ...]
    ) -> DocumentationGate:
        """Fail the gate on every defect the book's QA compile reports on a page the story touched."""
        pages = tuple(
            dict.fromkeys(
                node.partition("#")[0] for node in (*authored_nodes, *self.spec_nodes)
            )
        )
        gaps = self.call(
            compile_gaps,
            self.ctx.spec_dir,
            self.ctx.story_id or self.ctx.story_slug,
            pages,
        ).gaps
        if not gaps:
            return gate
        note = (
            f"The book does not compile into a QA plan: {len(gaps)} gap(s) on pages this "
            "story touched. Repair each on the page it names, as `<code> <obligation>: "
            "<what is missing>`:\n"
            + "\n".join(f"- {gap}" for gap in gaps)
        )
        notes = f"{gate.notes}\n\n{note}" if gate.status == "invalid" and gate.notes else note
        return DocumentationGate(
            status="invalid",
            notes=notes,
            changed_code_count=gate.changed_code_count,
            doctor_error_count=gate.doctor_error_count,
            failures=[*gate.failures, *(f"C:{gap}" for gap in gaps)],
        )

    def _with_exercise(self, gate: DocumentationGate, exercised: bool) -> DocumentationGate:
        """Run the book's compiled QA plan on the stack, and fail the gate on each scenario the product does not bear out."""
        spec_dir = self.ctx.spec_dir
        plan = Path(spec_dir) / QA_PLAN_FILE
        if plan.exists():
            self.logger.info("exercise skipped: %s stands, so QA owns the plan", plan)
            return gate
        story = self.ctx.story_id or self.ctx.story_slug
        if not self.call(compile_story_plan, spec_dir, story).compiled:
            self.logger.info("exercise skipped: the book compiled no QA plan")
            return gate
        lease = copy_lease(story, self.run_id, "docs")
        target = self.call(stack_target, self.ctx.story_slug, lease)
        started = time.monotonic()
        try:
            return self._exercise(gate, exercised, target.near, target.lease)
        finally:
            self.call(release_copy, near=target.near, lease=target.lease)
            plan.unlink(missing_ok=True)
            self.logger.info("exercise took %.0fs", time.monotonic() - started)

    def _exercise(
        self, gate: DocumentationGate, exercised: bool, near: str, lease: str
    ) -> DocumentationGate:
        stack = self.call(ensure_stack, near=near, lease=lease)
        if stack.ready not in ("yes", "unneeded"):
            self.logger.info("exercise skipped: the QA stack is not up (%s)", stack.ready)
            return gate
        run = self.call(
            run_qa_plan, self.ctx.spec_dir, near=near, lease=lease, label=EXERCISE_LABEL
        )
        if run.status == "passed":
            self.logger.info("exercise: the compiled plan passes on the stack")
            return gate
        ids = failed_scenario_ids(run) if run.status == "failed" else []
        if not ids:
            self.logger.info("exercise: the run ended %s and named no failed scenario", run.status)
            return self._unrunnable(gate, run.status, run.notes)
        if exercised:
            self.logger.info(
                "exercise: %d scenario(s) still fail after one bounce, QA owns them now: %s",
                len(ids),
                ", ".join(ids),
            )
            return gate
        note = exercise_text(
            self.ctx.spec_dir, failed_scenarios_arg(self.ctx.spec_dir, ids, EXERCISE_LABEL)
        )
        return DocumentationGate(
            status="invalid",
            notes=note,
            changed_code_count=gate.changed_code_count,
            doctor_error_count=gate.doctor_error_count,
            failures=[*gate.failures, *(f"X:{sid}" for sid in ids)],
        )

    @staticmethod
    def _unrunnable(gate: DocumentationGate, status: str, message: str) -> DocumentationGate:
        note = f"The compiled QA plan could not run: the run ended {status}."
        if message:
            note = f"{note}\n\n{message}"
        return DocumentationGate(
            status="invalid",
            notes="\n\n".join(part for part in (gate.notes, note) if part),
            changed_code_count=gate.changed_code_count,
            doctor_error_count=gate.doctor_error_count,
            failures=[*gate.failures, f"E:exercise-{status}"],
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
            args=resolver_args(self, block_kind="docs", notes=notes),
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
            services_root(self),
            tuple(classification.source_roots),
            TRUNK,
            "WORKTREE",
            preexisting=tuple(self.preexisting),
            story_sources=(
                self.output(resolve_story_sources).sources
                if self.workspace and self.ctx.story_id
                else ()
            ),
            story_refs=tuple(
                dict.fromkeys(ref for ref in (self.ctx.story_id, self.ctx.story_slug) if ref)
            ),
        )

    def _context_mode(
        self, classification: ContextClassification
    ) -> Literal["local", "semantic", "error"]:
        """Treat an explicit external repository packet as locally verifiable."""
        if (
            self.workspace
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
            self.ctx.spec_dir,
            mode,
            build_status,
            preexisting=tuple(self.preexisting),
        )

    @property
    def _epic_path(self) -> str:
        """The parent epic whose user journeys this story advances."""
        root = Path(find_docs_root(self.repo_dir))
        return f"{paths.epic_dir_rel(root, self.ctx.story_epic)}/epic.md"


__all__ = ["Docs"]
