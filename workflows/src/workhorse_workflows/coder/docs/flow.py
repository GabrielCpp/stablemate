"""One docs owner specifies a story in the Python book before any code, and the run checks it."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import PositiveInt
from workhorse._vendor.stablemate_core import books
from workhorse.pyflow import AgentTimeout, Await, Continue, Done, WorkflowFailed
from workhorse_workflows.kit import find_book_package, find_book_root, find_docs_root
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.book_qa.nodes import covered_services, verify_book_spec
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    TURN_MINUTES,
    cut_notes,
    owner_profile,
    turn_seconds,
)
from workhorse_workflows.coder.shared.resolution import (
    ResolverCut,
    answered,
    Resolving,
)
from workhorse_workflows.coder.shared.story import (
    prepare_story,
    resolve_workspace_dirs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.schemas.docs import DocsResult, SpecResult
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit.telemetry import counter_labels


def unbooked_message(names: list[str], service_books: Path) -> str:
    """The refusal for a story that names a service with no executable book."""
    named = ", ".join(f"`{name}`" for name in names)
    return (
        f"{named} has no book: no `{service_books}/<name>/service.py` and no "
        f"`{service_books}/<name>/*/service.py`. Write it with "
        "`workhorse-okf-book run python_book`, then run the story again."
    )


class Docs(Resolving):
    """Specify one story in the Python book, and gate the book with `ostler book check`."""

    story: str = ""
    epic: str = ""
    target_env: str = "local"
    preexisting: tuple[str, ...] = ()
    operator_mode: str = "auto"
    turn_minutes: PositiveInt = TURN_MINUTES

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks", "number")

    @property
    def _turn_s(self) -> float:
        return turn_seconds(self.turn_minutes)

    def setup(self) -> StoryPaths:
        """Resolve the workspace to directories and the story to its id and paths."""
        self.call(resolve_workspace_dirs)
        story = self.call(prepare_story, self.story, self.epic)
        self.call(covered_services, list(story.story_services))
        return story

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "docs", self.BUDGET_LABELS)

    @property
    def _chain(self) -> str:
        """The docs owner's own session, keyed per story."""
        return f"docs-spec:{self.ctx.story_slug}"

    def _ends(self, result: DocsResult) -> Done:
        """End the flow, and the story's docs session with it."""
        self.reset_session(self._chain)
        return Done(result)

    @property
    def _book(self) -> list[str]:
        """The story's services that have an executable book."""
        return list(self.output(covered_services).services)

    @property
    def _unbooked(self) -> list[str]:
        """The story's services that have no executable book, in the order the story names them."""
        book = self._book
        return [name for name in dict.fromkeys(self.ctx.story_services) if name not in book]

    def start(self) -> Continue | Done:
        """Refuse a story whose service has no book, and skip one that names no service."""
        self.reset_session(self._chain)
        if not self.ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r}. The story could not be resolved, so "
                "there is nothing to document."
            )
        if self._unbooked:
            raise WorkflowFailed(unbooked_message(self._unbooked, find_book_root(self.repo_dir) / books.package_folder(find_book_package(self.repo_dir))))
        if not self.ctx.story_services:
            return self._ends(
                DocsResult(
                    status="not_applicable",
                    notes="the story names no service, so there is no book to specify",
                )
            )
        return Continue(self.output(covered_services), self.work)

    def work(
        self,
        report: str = "",
        operator_context: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the owner turn: its subagents write the story into the book, review it and fix it."""
        self.logger.info("specifying %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "specify-story", returns=SpecResult)
        try:
            result: SpecResult = self.agent(
                turn.prompt,
                returns=turn.returns,
                power="high",
                timeout=self._turn_s,
                deadline=self._turn_s,
                silence=SILENCE_S,
                profile=owner_profile("docs"),
                session=self._chain,
                add_dirs=workspace_dirs(self),
                args=turn.args
                | {"book_services": self._book}
                | self._spec_brief()
                | {"report": report, "operator_context": operator_context},
            )
        except AgentTimeout as exc:
            return self._ask(cut_notes("The docs turn", exc), "the docs turn", blocks)
        if result.blocked:
            return self._block(result, result.notes, "the docs turn", blocks)
        return Continue(result, self.check, author=result, laps=laps, blocks=blocks)

    def _spec_brief(self) -> dict[str, object]:
        """What the spec pass reads before it writes a word: the story and the book, with no diff yet."""
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "docs_root": str(find_docs_root(self.repo_dir)),
            "book_root": str(find_book_root(self.repo_dir)),
            "service_package": find_book_package(self.repo_dir),
            "service_books": str(find_book_root(self.repo_dir) / books.package_folder(find_book_package(self.repo_dir))),
            "epic_path": self._epic_path,
        }

    def check(self, author: SpecResult, laps: int = 0, blocks: int = 0) -> Continue | Await | Done:
        """Check the book with `ostler book check`, and send what failed back to the owner."""
        gate = self.call(verify_book_spec, self._book, author.status)
        if gate.status == "passed":
            return Continue(gate, self.finish, notes=gate.notes or author.notes)
        if laps >= MAX_LAPS:
            notes = f"{gate.notes}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(gate, notes, "the checks", blocks)
        return Continue(gate, self.work, report=gate.notes, laps=laps + 1, blocks=blocks)

    def finish(self, notes: str = "") -> Done:
        """Hand back the verdict now that the gate holds."""
        self.logger.info("specification passed for %s", self.ctx.story_slug)
        return self._ends(DocsResult(status="passed", notes=notes))

    def _block(self, result: object, notes: str, where: str, blocks: int) -> Continue | Await:
        self.logger.info("documentation blocked on %s: %s", self.ctx.story_slug, notes)
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks)
        return Continue(result, self.resolve, notes=notes, where=where, blocks=blocks)

    def _ask(
        self,
        notes: str,
        where: str,
        blocks: int,
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
        )

    def resolve(self, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self._resolver_turn(
            block_kind="docs",
            notes=notes,
            add_dirs=workspace_dirs(self),
        )
        if isinstance(result, ResolverCut):
            return self._ask(result.notes, where, blocks)
        if answered(self, result, "docs"):
            return Continue(result, self.read_operator, notes=notes, blocks=blocks + 1)
        return self._ask(notes, where, blocks, result)

    def read_operator(self, notes: str = "", blocks: int = 0) -> Continue | Done:
        """Resume the owner's session with the answer in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the documentation block to the epic")
            return self._ends(DocsResult(status="blocked", notes=answer.content or notes))
        return Continue(
            answer,
            self.work,
            operator_context=answer.content,
            blocks=blocks,
        )

    @property
    def _epic_path(self) -> str:
        """The parent epic whose user journeys this story advances."""
        root = Path(find_docs_root(self.repo_dir))
        return f"{paths.epic_dir_rel(root, self.ctx.story_epic)}/epic.md"


__all__ = ["Docs", "unbooked_message"]
