"""The agent-CLI port: one interface the controller drives, whatever CLI is behind it.

The resilience ladder in ``ladder.py`` (transient/cap retries, context-overflow
compaction, prompt reframing, default-to-next) is CLI-agnostic and delegates the
two operations that ARE CLI-specific to the active backend:

* ``run_turn`` — run one non-interactive turn and return its final text.
* ``compact``  — best-effort context compaction (``False`` when unsupported, in
  which case the ladder reframes instead).

The backend is chosen per-run via the ``AGENT_CLI`` env var (or ``--cli``), so a
single workflow runs entirely on one CLI. The *model* is selectable per node via a
node's ``model:`` map (a per-CLI map, e.g. ``{claude: opus, cline: openrouter/...}``;
see ``runner/ladder.py``). To run a node on an OpenRouter model, point an
OpenRouter-native backend (``cline`` / ``opencode``) at it with ``--cli`` (or
``AGENT_CLI``, which is what farrier's generated Makefile sets) and give the node
an ``openrouter/<slug>`` model — no proxy, since those CLIs talk to OpenRouter
directly and cache natively.

This module declares the port and nothing else: each CLI owns its protocol in its
own sibling module (``claude``, ``codex``, ``copilot``, ``opencode``, ``cline``),
and ``registry`` — the only module that imports all of them — maps a name to a
class. Importing the port therefore drags in no adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from workhorse._vendor.stablemate_core.config import resolve_harness_env
from workhorse.runner.failure import BackendInvocationError

if TYPE_CHECKING:
    # Annotation-only, and load-bearing that it stays that way: ``config_run`` holds
    # the run's assembled settings, which now name a backend (the null adapter that
    # stands for "no CLI selected"). A runtime import here would close that into a
    # cycle. Nothing in this module *uses* the type — it only types two signatures.
    from workhorse.config_run import AgentResilience


# Linux permits an argv vector much larger than any one argument. Keep file-backed
# delivery comfortably below the common 128 KiB per-argument ceiling.
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
    """One agent CLI behind a uniform interface. Stateless — safe to share.

    An ABC rather than a Protocol because the port carries shared behaviour every
    adapter inherits: ``harness_env`` below.
    """

    #: Short name used in logs and the ``AGENT_CLI`` registry key.
    name: str = "agent"
    #: Model used when a node declares no ``model:`` and no env override is set.
    default_model: str | None = None
    #: Whether the CLI can compact a long session in place. When False the
    #: resilience ladder reframes on context overflow instead of compacting.
    supports_compaction: bool = False

    def harness_env(self) -> dict[str, str]:
        """Operator-configured extra environment for this CLI (``[harness.<name>].env``).

        Read per turn rather than once at startup: a config read is one small TOML
        parse against a turn measured in minutes, and a week-long run picks up an
        edit at its next node instead of needing a restart.

        A backend knows its own ``name``, so it resolves its own env and hands it to
        the spawn helper. That keeps ``run_turn``'s signature — implemented five times
        and faked once more per test that supplies a mock backend — free of a parameter
        every implementation would only pass straight through.
        """
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
        """Run one non-interactive turn for ``prompt`` and return the final result
        text. Persist the session id (when the CLI supports resume) to
        ``session_id_path``. Raise ``failure.BackendInvocationError`` on failure,
        classifying it as ``transient`` / ``overflow`` / cap (``reset_at``) so the
        ladder can recover appropriately.

        ``prompt_path`` is the persisted full prompt available for file-backed
        delivery when an argv-only harness would exceed its argument limit.
        ``cwd`` sets the subprocess working directory (controls CLAUDE.md/skills
        discovery). ``add_dirs`` are additional directories the agent can access
        (passed as --add-dir flags to Claude). ``effort`` is the node's reasoning
        effort ("low"/"medium"/"high"); each backend translates it (thinking
        directive for Claude/Copilot, ``model_reasoning_effort`` for Codex)."""

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
        """Best-effort: compact the node's session to free context so it can
        continue. Return True when compaction ran, False when it could not (no
        session, failure) or is unsupported — callers then fall back to reframe."""
