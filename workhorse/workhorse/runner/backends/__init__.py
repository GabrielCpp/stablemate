"""The agent-CLI port: one interface the controller drives, whatever CLI is behind it."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from workhorse._vendor.stablemate_core.profiles import resolve_harness_env
from workhorse.runner.acp import NullTranscript, TranscriptMapper
from workhorse.runner.failure import BackendInvocationError

if TYPE_CHECKING:
    from workhorse.config_run import AgentResilience
    from workhorse.runner.backends.delegates import Delegate


ARGV_PROMPT_LIMIT_BYTES = 96 * 1024


def operator_config_dirs(harness: str) -> tuple[Path, ...]:
    """The existing directories ``harness`` loads the operator's own config, skills, instructions and plugins from."""
    home = Path.home()
    candidates: list[Path] = []
    if harness == "claude":
        candidates = [Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")]
    elif harness == "codex":
        candidates = [Path(os.environ.get("CODEX_HOME") or home / ".codex"), home / ".agents"]
    elif harness == "opencode":
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        candidates = [config_home / "opencode", home / ".claude" / "skills", home / ".agents" / "skills"]
    return tuple(directory for directory in candidates if directory.is_dir())


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """A named, narrowed persona for one node's turns, as the CLI behind the port understands it.

    A tool the turn never calls is not free. Most CLIs resend every enabled tool's JSON
    schema on every step of a turn, so an unused tool is paid for once per step.
    ``tools`` maps a CLI tool name to whether this node may call it, and a backend may
    spend that as a removal from the request rather than a refusal at call time.
    ``steps`` bounds the agentic iterations one turn may take before it must answer in
    text. ``disable_mcp`` names MCP servers to leave unattached. Workhorse never authors
    a profile. A workflow knows which tools its own prompt needs, and hands one down on
    its node.

    A turn never loads less of the operator's environment than an interactive session of
    the same CLI: user settings, permission rules, hooks, model settings, skills,
    instruction files and plugins. ``confined`` narrows what the turn may write, read and
    run with a guard layered on top of that environment, and removes none of it. The
    directories the CLI loads the operator's config from stay readable
    (``operator_config_dirs``). A confined turn reads only its working directory, its
    added directories and those. The claude and codex backends write only in the working
    directory, and the opencode backend writes in the added directories too. ``tools``
    still turns tools off. ``commands`` names the only shell commands a confined turn may
    run, each with any arguments. With none named, the turn has no shell. The copilot and
    cline backends apply no box, so they warn that a confined turn runs with the
    operator's full permissions.

    ``command_timeout_s`` is the longest one shell command may run before the CLI stops
    waiting on it. A CLI that moves a slow command to the background hands the turn an
    empty result, and the turn goes on without the output it ran the command for. Keep
    it below the silence budget, since a command that runs quietly is silence.
    """

    name: str
    tools: dict[str, bool] = field(default_factory=dict)
    steps: int | None = None
    disable_mcp: tuple[str, ...] = ()
    tool_output_max_lines: int | None = None
    tool_output_max_bytes: int | None = None
    confined: bool = False
    commands: tuple[str, ...] = ()
    command_timeout_s: int | None = None

    def __post_init__(self) -> None:
        if self.commands and not self.confined:
            raise ValueError(
                f"agent '{self.name}' names commands but is not confined, so nothing would hold it to them"
            )


def warn_unenforced_confinement(cli: str, node_id: str, agent: AgentProfile | None) -> None:
    """Say that ``cli`` applies no box, so a confined profile's turn runs with the operator's full permissions."""
    if agent is not None and agent.confined:
        print(
            f"[{node_id}] ⚠ {cli} does not enforce a confined profile; the turn runs with the operator's full permissions",
            flush=True,
        )


def git_worktree(directory: Path) -> Path | None:
    """The nearest ancestor of ``directory`` holding ``.git``, or None when it lies in no worktree."""
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def prepare_argv_prompt(prompt: str, prompt_path: Path | None) -> tuple[str, Path | None]:
    """Return a bounded argv message and stage oversized content at ``prompt_path``."""
    if len(prompt.encode("utf-8")) <= ARGV_PROMPT_LIMIT_BYTES:
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
    if len(prompt.encode("utf-8")) > ARGV_PROMPT_LIMIT_BYTES and any(
        prompt in argument for argument in command
    ):
        raise RuntimeError("oversized prompt remained in the subprocess argument vector")


class AgentBackend(ABC):
    """One agent CLI behind a uniform interface."""

    name: str = "agent"
    default_model: str | None = None
    supports_compaction: bool = False
    supports_subagents: bool = False

    def harness_env(self) -> dict[str, str]:
        """Operator-configured extra environment for this CLI (``[harness.<name>].env``)."""
        return resolve_harness_env(self.name)

    def transcript_mapper(self) -> TranscriptMapper:
        """A fresh mapper from this CLI's events to ACP updates, for one turn. The default shows nothing."""
        return NullTranscript()

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
        agent: AgentProfile | None = None,
        delegates: tuple[Delegate, ...] = (),
    ) -> str:
        """Run one non-interactive turn for ``prompt`` and return the final result text.

        ``delegates`` are the subagents the turn may hand narrow work to. A backend
        defines them for its CLI at launch, or warns once that its CLI cannot.
        """

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
