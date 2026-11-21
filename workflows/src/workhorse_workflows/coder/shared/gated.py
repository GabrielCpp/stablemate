"""The block, ask and resolve states a flow with one story-bound owner shares: a block goes to the resolver, then to the operator."""
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import PositiveInt
from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    TURN_MINUTES,
    turn_seconds,
)
from workhorse_workflows.coder.shared.resolution import (
    ResolverCut,
    answered,
    Resolving,
)
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths


class Gated(Resolving):
    """The base of a flow whose blocks reach the operator. Its subclass names the block kind and writes `read_operator`."""

    target_env: str = "local"
    operator_mode: str = "auto"
    turn_minutes: PositiveInt = TURN_MINUTES

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    BLOCK_KIND: ClassVar[str]

    @property
    def _turn_s(self) -> float:
        """The wall-clock allowance of one turn of this flow, in seconds."""
        return turn_seconds(self.turn_minutes)

    def _dirs(self) -> list[str]:
        """The `add_dirs` every agent turn in this flow is given."""
        raise NotImplementedError

    def _gate_story(self) -> StoryPaths:
        """The story a block is about."""
        return self.ctx

    if TYPE_CHECKING:

        def read_operator(self, blocks: int = 0) -> Continue | Done: ...

    def _block(self, result: object, notes: str, where: str, blocks: int) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks)
        return Continue(result, self.resolve, notes=notes, where=where, blocks=blocks)

    def _ask(
        self, notes: str, where: str, blocks: int, result: OperatorResolution | None = None
    ) -> Await:
        story = self._gate_story()
        gate = escalation(
            self,
            block_kind=self.BLOCK_KIND,
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
            story=story,
        )
        return Await(
            context_path(self, story.story_path),
            gate.body,
            self.read_operator,
            blocks=blocks + 1,
        )

    def resolve(self, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self._resolver_turn(
            block_kind=self.BLOCK_KIND,
            notes=notes,
            add_dirs=self._dirs(),
            story=self._gate_story(),
        )
        if isinstance(result, ResolverCut):
            return self._ask(result.notes, where, blocks)
        if answered(self, result, self.BLOCK_KIND):
            return Continue(result, self.read_operator, blocks=blocks + 1)
        return self._ask(notes, where, blocks, result)


__all__ = ["Gated"]
