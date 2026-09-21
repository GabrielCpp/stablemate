"""The agent-CLI port: one interface the controller drives, whatever CLI is behind it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from workhorse._vendor.stablemate_core.config import resolve_harness_env
from workhorse.runner.failure import BackendInvocationError

if TYPE_CHECKING:
    from workhorse.config_run import AgentResilience


INLINE_PROMPT_LIMIT_BYTES = 96 * 1024


def prepare_argv_prompt(prompt: str, prompt_path: Path | None) -> tuple[str, Path | None]:
    """Return a bounded argv message and stage oversized content at ``prompt_path``."""
    if len(prompt.encode("utf-8")) <= INLINE_PROMPT_LIMIT_BYTES:
        return prompt, None
    if prompt_path is None:
        raise BackendInvocationError(
            "an oversized prompt needs a prompt artifact path for file-backed delivery"
        )
    prompt_path.write_text(prompt, encoding="utf-8")
    message = (
        "The complete prompt for this turn is in the attached file at "
        f"{prompt_path}. Read it in full and follow it as the user request."
    )
    return message, prompt_path


def ensure_prompt_is_not_in_argv(prompt: str, command: list[str]) -> None:
    """Enforce the transport invariant before spawning an argv-based harness."""
    if len(prompt.encode("utf-8")) > INLINE_PROMPT_LIMIT_BYTES and any(
        prompt in argument for argument in command
    ):
        raise RuntimeError("oversized prompt remained in the subprocess argument vector")


class AgentBackend(ABC):
    """One agent CLI behind a uniform interface."""

    name: str = "agent"
    default_model: str | None = None
    supports_compaction: bool = False

    def harness_env(self) -> dict[str, str]:
        """Operator-configured extra environment for this CLI (``[harness.<name>].env``)."""
        return resolve_harness_env(self.name)

    @abstractmethod
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
        """Run one non-interactive turn for ``prompt`` and return the final result text."""

    @abstractmethod
    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        """Best-effort: compact the node's session to free context so it can continue."""
