"""The story params, gates and operator loop that the QA flows share: one seat per story, a lap budget and a resolver before the operator."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, WorkflowFailed

from workhorse_workflows.coder.shared import work
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.gated import Gated
from workhorse_workflows.coder.shared.owner import (
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared.schemas.qa import QaFlowResult, QaFlowStatus
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.coder.shared.stack import (
    ensure_stack,
    hold_copy,
    release_copy,
    stack_target,
)
from workhorse_workflows.coder.shared.story import prepare_story
from workhorse_workflows.kit.telemetry import counter_labels


class QaOwner(Gated):
    """The base of a flow that judges one story through one owner session. Its subclass names the label prefix and writes the `work` state."""

    story: str = ""
    epic: str = ""
    preexisting: tuple[str, ...] = ()

    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack, hold_copy, release_copy})

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks")

    BLOCK_KIND: ClassVar[str] = "qa"

    LABEL_PREFIX: ClassVar[str]

    if TYPE_CHECKING:

        def work(self, *args: Any, **kwargs: Any) -> Continue | Await: ...

    def setup(self) -> StoryPaths:
        """Resolve the slug to the story path, its spec dir and its services."""
        ctx = self.call(prepare_story, self.story, self.epic)
        if not ctx.story_path:
            raise WorkflowFailed(
                f"no story path for {self.story!r}. The story could not be resolved, so "
                "there is nothing to QA."
            )
        return ctx

    def labels(self) -> dict[str, str]:
        """Which story this run is on: what the run's activity line shows."""
        return {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, self.LABEL_PREFIX, self.BUDGET_LABELS)

    @property
    def _session(self) -> str:
        return f"{self.LABEL_PREFIX}:{self.ctx.story_slug}"

    def _dirs(self) -> list[str]:
        """The repos this story's plan touches: every agent turn's `add_dirs`."""
        return list(self.output(resolve_impl_context).affected_repo_paths)

    def _release(self) -> None:
        """Tear down this run's stack copy: the next pass QAs changed code, so it builds a new one."""
        target = self.output(stack_target)
        self.call(release_copy, near=target.near, lease=target.lease)

    def _retire(self, status: QaFlowStatus) -> None:
        """Release the stack copy, and end the owner's session unless the developer takes the findings."""
        self._release()
        if status != "refix":
            self.reset_session(self._session)

    def _owner_options(self) -> dict[str, Any]:
        """What every owner turn is given besides its prompt, contract and arguments."""
        return {
            "power": "high",
            "timeout": UNBOUNDED,
            "silence": SILENCE_S,
            "profile": owner_profile("qa"),
            "session": self._session,
            "add_dirs": self._dirs(),
        }

    def _lap(
        self, result: object, failures: list[str], laps: int, blocks: int, **work_args: Any
    ) -> Continue | Await:
        text = "\n\n".join(failures)
        if laps >= MAX_LAPS:
            notes = f"{text}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(result, notes, "the checks", blocks)
        return Continue(result, self.work, report=text, laps=laps + 1, blocks=blocks, **work_args)

    def read_operator(self, blocks: int = 0) -> Continue | Done:
        """Log the answer, then resume the owner's session with it in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        work.log_answer(self.run_dir, f"{self.ctx.story_slug}: {answer.scope}", answer.content)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the answer to the epic, so the run replans")
            self.reset_session(self._session)
            self._release()
            return Done(QaFlowResult(status="replan", operator_notes=answer.content))
        return Continue(answer, self.work, operator_context=answer.content, blocks=blocks)


__all__ = ["QaOwner"]
