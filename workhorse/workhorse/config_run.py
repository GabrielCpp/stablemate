"""Immutable per-run configuration for the workhorse driver.

Everything the driver used to read ad-hoc from ``os.environ`` at run time is
captured ONCE here, at the CLI boundary, in a frozen ``RunConfig``. The driver
and the agent ladder then read from this object rather than the environment, so a
run's configuration is immutable by design and a test can drive a workflow
in-process with explicit values instead of mutating global state.

``from_env`` is the *only* place these variables are read: ``runner/ladder.py``
holds no import-time constants of its own, so the names and defaults documented in
``docs/GUARDRAILS.md`` have exactly one implementation and a caller that passes no
config gets the dataclass defaults rather than whatever the environment said when
the module happened to be imported.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from workhorse.runner.backends import AgentBackend


def _int(environ: Mapping[str, str], key: str, default: int) -> int:
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(environ: Mapping[str, str], key: str, default: float) -> float:
    raw = (environ.get(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool(environ: Mapping[str, str], key: str, default: bool) -> bool:
    raw = (environ.get(key) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no")


@dataclass(frozen=True)
class AgentResilience:
    """The agent-node recovery ladder's tuning knobs (see runner/ladder.py).

    One field per ``AGENT_*`` env var. Built by :meth:`from_env` at the CLI
    boundary; the driver threads it into ``run_agent`` so the reframe/retry/cap
    behavior is set explicitly rather than by import-time module constants — which
    is what lets an in-process test neutralize the recovery sleeps without touching
    the environment.
    """

    #: Additional attempts when Claude's response can't be parsed into the node's
    #: declared outputs.
    max_output_retries: int = 2
    #: Additional attempts when the agent-CLI call itself fails for a *transient*
    #: reason (rate limit, overload, network blip). Each retry waits
    #: min(base * 2**attempt, cap) seconds.
    max_invoke_retries: int = 4
    #: When invocation + output parsing still fail after the transient retries,
    #: REFRAME the prompt from scratch in a fresh session and try the node again, up
    #: to this many times. A node Claude can't answer as-phrased often succeeds when
    #: re-asked more simply.
    max_rephrase_attempts: int = 3
    #: When a node exhausts the model's context window and the headless CLI returns
    #: instead of auto-compacting, COMPACT the session and continue (preserving the
    #: node's progress) this many times before falling through to the reframe
    #: ladder. 0 disables compaction recovery (straight to reframe).
    max_compact_attempts: int = 2
    #: Final resilience layer: when every reframing fails, return safe default
    #: outputs so the controller advances to the node's ``next`` instead of crashing
    #: the run. This worker runs autonomously for days — a single unanswerable node
    #: must degrade to "continue". Disable only when a hard stop is wanted.
    use_default_outputs: bool = True
    #: Default per-node wall-clock budget for a single agent turn when the node does
    #: not set its own ``timeout`` (seconds). 1h is long enough for a heavy QA /
    #: build / browser node, short enough that a wedged turn is force-killed and
    #: retried within the hour. Nodes may override per-node (incl. ``infinity``).
    result_timeout_s: float = 3600.0
    invoke_backoff_base_s: float = 15.0
    invoke_backoff_cap_s: float = 300.0
    #: Hard backstop for the per-node timeout. The in-loop ``elapsed > timeout``
    #: check can only fire BETWEEN reads — if the agent writes a partial line and
    #: then its socket wedges (a stalled API stream, a hung MCP server), the reader
    #: blocks inside readline() and the wall-clock check never runs again. A watchdog
    #: on a SEPARATE thread SIGKILLs the whole process group once the turn overruns
    #: its budget by this grace, regardless of stream state.
    watchdog_grace_s: float = 120.0
    #: Optional idle cutoff: treat a turn that has produced no stream event for this
    #: long as stalled. Default 0 = disabled, because a legitimate long tool call
    #: (e.g. a multi-minute ``make test``) emits nothing until it returns and must
    #: not be killed; the watchdog above is the always-on backstop.
    idle_timeout_s: float = 0.0
    cap_default_wait_s: float = 3600.0
    cap_wait_margin_s: float = 120.0
    cap_tick_s: float = 600.0
    max_cap_waits: int = 48
    cap_max_wait_s: float = float(8 * 24 * 3600)
    #: The agent CLI can be replaced ON DISK mid-run — Claude Code ships a native
    #: binary and self-updates by default, and a manual ``npm i -g`` does the same.
    #: While that in-place rewrite is in flight, exec of the very same path fails for
    #: a sub-second window (ETXTBSY / ENOENT during the rename / ENOEXEC on a
    #: half-written header). That is NOT a missing tool, so a few short retries ride
    #: the update out instead of crashing an otherwise-healthy turn.
    exec_retry_max: int = 5
    exec_retry_base_s: float = 1.0
    exec_retry_cap_s: float = 8.0
    #: How often the streaming loop emits a turn-liveness heartbeat metric. It only
    #: REPORTS the idleness the loop already tracks — it never kills anything — so it
    #: is safe on by default (and a no-op when telemetry is off). Kept well under
    #: groom's stall window so a live turn is provably alive long before the alerter
    #: would page. Shares ``WORKHORSE_OTEL_HEARTBEAT_S`` with the metric exporter.
    heartbeat_every_s: float = 10.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AgentResilience:
        e = os.environ if environ is None else environ
        return cls(
            max_output_retries=_int(e, "AGENT_MAX_OUTPUT_RETRIES", 2),
            max_invoke_retries=_int(e, "AGENT_MAX_INVOKE_RETRIES", 4),
            max_rephrase_attempts=_int(e, "AGENT_MAX_REPHRASE_ATTEMPTS", 3),
            max_compact_attempts=_int(e, "AGENT_MAX_COMPACT_ATTEMPTS", 2),
            use_default_outputs=_bool(e, "AGENT_USE_DEFAULT_OUTPUTS", True),
            result_timeout_s=_float(e, "AGENT_RESULT_TIMEOUT_S", 3600.0),
            invoke_backoff_base_s=_float(e, "AGENT_INVOKE_BACKOFF_BASE_S", 15.0),
            invoke_backoff_cap_s=_float(e, "AGENT_INVOKE_BACKOFF_CAP_S", 300.0),
            watchdog_grace_s=_float(e, "AGENT_WATCHDOG_GRACE_S", 120.0),
            idle_timeout_s=_float(e, "AGENT_IDLE_TIMEOUT_S", 0.0),
            cap_default_wait_s=_float(e, "AGENT_CAP_DEFAULT_WAIT_S", 3600.0),
            cap_wait_margin_s=_float(e, "AGENT_CAP_WAIT_MARGIN_S", 120.0),
            cap_tick_s=_float(e, "AGENT_CAP_TICK_S", 600.0),
            max_cap_waits=_int(e, "AGENT_MAX_CAP_WAITS", 48),
            cap_max_wait_s=_float(e, "AGENT_CAP_MAX_WAIT_S", float(8 * 24 * 3600)),
            exec_retry_max=_int(e, "AGENT_EXEC_RETRY_MAX", 5),
            exec_retry_base_s=_float(e, "AGENT_EXEC_RETRY_BASE_S", 1.0),
            exec_retry_cap_s=_float(e, "AGENT_EXEC_RETRY_CAP_S", 8.0),
            heartbeat_every_s=_float(e, "WORKHORSE_OTEL_HEARTBEAT_S", 10.0),
        )

    def with_overrides(self, **kwargs: Any) -> AgentResilience:
        """A copy with some fields replaced — used by the test harness to zero the
        recovery sleeps (e.g. ``max_rephrase_attempts=0``) without env mutation."""
        return replace(self, **kwargs)


@dataclass(frozen=True)
class RunConfig:
    """Immutable configuration for one run.

    Built once by :meth:`from_env` (the CLI boundary in ``main()``), then read by the
    driver instead of ``os.environ``. Tests construct it directly with a
    ``backend_factory`` (a mock backend) to drive a workflow hermetically.
    """

    resilience: AgentResilience = field(default_factory=AgentResilience)
    #: Absolute wall-clock ceiling in seconds (WORKHORSE_MAX_RUNTIME_S); 0 = unbounded.
    max_runtime_s: float = 0.0
    #: Resolves the active agent backend by name. Overridden by the test harness to
    #: return a mock backend; ``None`` means "use runner.backends.registry.get_backend".
    backend_factory: Callable[[str | None], AgentBackend] | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RunConfig:
        e = os.environ if environ is None else environ
        return cls(
            resilience=AgentResilience.from_env(e),
            max_runtime_s=_configured_max_runtime_s(e),
        )

    def get_backend(self, cli: str | None = None) -> AgentBackend:
        """Resolve the backend for this run via ``backend_factory`` or the default."""
        if self.backend_factory is not None:
            return self.backend_factory(cli)
        # Deferred because the registry imports every adapter and each adapter
        # imports this module for ``AgentResilience`` — a genuine runtime cycle, not
        # a layering shortcut. The fix is for RunConfig to be *given* a backend at
        # the CLI boundary rather than resolve one; that is the cli/ split's job.
        from workhorse.runner.backends.registry import get_backend

        return get_backend()


def _configured_max_runtime_s(environ: Mapping[str, str]) -> float:
    raw = (environ.get("WORKHORSE_MAX_RUNTIME_S") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0
