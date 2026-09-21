"""The absence of an agent CLI, as an adapter rather than as ``None``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from workhorse.runner.backends import AgentBackend
from workhorse.runner.failure import BackendInvocationError

if TYPE_CHECKING:
    from workhorse.config_run import AgentResilience


class NullBackend(AgentBackend):
    """Fails every turn with an actionable message, in the ladder's own vocabulary."""

    name = "none"
    default_model = None
    supports_compaction = False

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        prompt_path: Path | None = None,
        timeout: float,
        resilience: AgentResilience,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        raise BackendInvocationError(
            f"node {node_id!r} needs an agent CLI and this run has none — "
            f"pass --cli or set AGENT_CLI"
        )

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        return False
