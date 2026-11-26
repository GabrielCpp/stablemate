"""Name → backend class."""

from __future__ import annotations

import os

from workhorse._vendor.stablemate_core.harness import workhorse_harnesses
from workhorse._vendor.stablemate_core.profiles import resolve_default_cli
from workhorse._vendor.stablemate_core.schema import HomeConfig
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.antigravity import AntigravityBackend
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.copilot import CopilotBackend
from workhorse.runner.backends.opencode import OpenCodeBackend
from workhorse.runner.backends.pi import PiBackend

_REGISTRY: dict[str, type[AgentBackend]] = {
    "antigravity": AntigravityBackend,
    "claude": ClaudeBackend,
    "codex": CodexBackend,
    "copilot": CopilotBackend,
    "opencode": OpenCodeBackend,
    "pi": PiBackend,
}

_CACHE: dict[str, AgentBackend] = {}


def backend_names() -> list[str]:
    """Every selectable backend name, sorted."""
    return sorted(_REGISTRY)


def active_cli(name: str | None = None, home: HomeConfig | None = None) -> str:
    """The CLI a run drives: explicit ``name`` → ``AGENT_CLI`` → config → built-in."""
    return (name or os.environ.get("AGENT_CLI") or resolve_default_cli(home)).strip().lower()


def get_backend(name: str | None = None) -> AgentBackend:
    """The backend ``active_cli`` picks for ``name``."""
    resolved = active_cli(name)
    if resolved not in _REGISTRY:
        available = ", ".join(sorted(harness.name for harness in workhorse_harnesses()))
        raise ValueError(
            f"unknown CLI backend {resolved!r} (set AGENT_CLI, --cli or the config's "
            f"default_cli to one of: {available})"
        )
    if resolved not in _CACHE:
        _CACHE[resolved] = _REGISTRY[resolved]()
    return _CACHE[resolved]
