"""The absence of an agent CLI, as an adapter rather than as ``None``.

A run may legitimately have no agent in it: a dry run, or a test driving script
nodes only. That used to be spelled ``RunConfig.backend = None``, which made every
holder of a backend nullable in principle and non-nullable in practice —
``AgentRunner.backend`` is typed ``AgentBackend`` and every ladder path calls
``self.backend.name`` unguarded, so an agentless run that reached an agent node
died on an ``AttributeError`` rather than on a sentence.

So absence is an implementation of the port instead. Nothing branches on it: the
field's type is the port, the ladder drives it like any other CLI, and the one
place that knows what "no CLI" means is here.

It is deliberately NOT in ``registry``: this is not a CLI an operator can select
with ``AGENT_CLI``, it is what a run has when nobody selected one.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from workhorse.runner.backends import AgentBackend
from workhorse.runner.failure import BackendInvocationError

if TYPE_CHECKING:
    from workhorse.config_run import AgentResilience


class NullBackend(AgentBackend):
    """Fails every turn with an actionable message, in the ladder's own vocabulary.

    The failure is non-transient and non-overflow, which is the ladder's existing
    "non-recoverable CLI failure" branch: it aborts the run cleanly at the first
    agent node instead of reframing three times and then defaulting the node's
    outputs. That is the right reading — no amount of rephrasing supplies a CLI,
    and defaulting past an agent node would advance a run on fabricated outputs.
    """

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
