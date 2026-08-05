"""Name → backend class. The only module that imports every adapter.

It is deliberately not ``__init__.py``: a registry has to import all of them, so
putting it beside the port would make ``from workhorse.runner.backends import
AgentBackend`` drag in every CLI. The port declares, the adapters implement, this
chooses.
"""

from __future__ import annotations

import os

from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.cline import ClineBackend
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.copilot import CopilotBackend
from workhorse.runner.backends.opencode import OpenCodeBackend

# Registry of available backends, keyed by their AGENT_CLI name.
_REGISTRY: dict[str, type[AgentBackend]] = {
    "claude": ClaudeBackend,
    "codex": CodexBackend,
    "copilot": CopilotBackend,
    "cline": ClineBackend,
    "opencode": OpenCodeBackend,
}

_CACHE: dict[str, AgentBackend] = {}


def get_backend(name: str | None = None) -> AgentBackend:
    """Resolve the active backend: explicit ``name`` → ``AGENT_CLI`` env → ``claude``.

    Backends are stateless, so a per-name cached instance is reused. Raises
    ``ValueError`` (fail fast) on an unknown name."""
    resolved = (name or os.environ.get("AGENT_CLI") or "claude").strip().lower()
    if resolved not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown CLI backend {resolved!r} (set AGENT_CLI to one of: {available})"
        )
    if resolved not in _CACHE:
        _CACHE[resolved] = _REGISTRY[resolved]()
    return _CACHE[resolved]
