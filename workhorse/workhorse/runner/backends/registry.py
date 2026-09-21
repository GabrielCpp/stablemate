"""Name → backend class."""

from __future__ import annotations

import os

from workhorse._vendor.stablemate_core.config import resolve_default_cli
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.cline import ClineBackend
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.copilot import CopilotBackend
from workhorse.runner.backends.opencode import OpenCodeBackend

_REGISTRY: dict[str, type[AgentBackend]] = {
    "claude": ClaudeBackend,
    "codex": CodexBackend,
    "copilot": CopilotBackend,
    "cline": ClineBackend,
    "opencode": OpenCodeBackend,
}

_CACHE: dict[str, AgentBackend] = {}


def backend_names() -> list[str]:
    """Every selectable backend name, sorted."""
    return sorted(_REGISTRY)


def get_backend(name: str | None = None) -> AgentBackend:
    """Resolve the active backend: explicit ``name`` → ``AGENT_CLI`` → config → built-in."""
    resolved = (name or os.environ.get("AGENT_CLI") or resolve_default_cli()).strip().lower()
    if resolved not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown CLI backend {resolved!r} (set AGENT_CLI, --cli or the config's "
            f"default_cli to one of: {available})"
        )
    if resolved not in _CACHE:
        _CACHE[resolved] = _REGISTRY[resolved]()
    return _CACHE[resolved]
