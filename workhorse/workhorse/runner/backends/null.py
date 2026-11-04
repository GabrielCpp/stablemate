"""The absence of an agent CLI, as an adapter rather than as ``None``."""

from __future__ import annotations

from workhorse.runner.backends import AgentBackend, TurnRequest
from workhorse.runner.failure import BackendInvocationError


class NullBackend(AgentBackend):
    """Fails every turn with an actionable message, in the ladder's own vocabulary."""

    name = "none"
    default_model = None
    supports_compaction = False
    supports_subagents = False

    def execute(self, turn: TurnRequest) -> str:
        raise BackendInvocationError(
            f"node {turn.node_id!r} needs an agent CLI and this run has none — "
            f"pass --cli or set AGENT_CLI"
        )
