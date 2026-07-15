"""Immutable per-run configuration for the workhorse engine.

Everything the engine used to read ad-hoc from ``os.environ`` at run time is
captured ONCE here, at the CLI boundary, in a frozen ``RunConfig``. The graph
walk (``Workhorse`` in ``main.py``) and the agent ladder then read from this
object rather than the environment, so a run's configuration is immutable by
design and a test can drive the engine in-process with explicit values instead
of mutating global state.

The env-var names and defaults mirror the module constants in
``runner/agent.py`` (which remain for direct callers of ``run_agent`` and are
documented in ``docs/GUARDRAILS.md``); ``from_env`` is the single authoritative
place the engine resolves them.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runner.backends import AgentBackend
    from .runner.script import ScriptRunner


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
    """The agent-node recovery ladder's tuning knobs (see runner/agent.py).

    One field per ``AGENT_*`` env var. Built by :meth:`from_env` at the CLI
    boundary; the ``Workhorse`` engine threads it into ``run_agent`` so the
    reframe/retry/cap behavior is set explicitly rather than by import-time
    module constants — which is what lets an in-process test neutralize the
    recovery sleeps without touching the environment.
    """

    max_output_retries: int = 2
    max_invoke_retries: int = 4
    max_rephrase_attempts: int = 3
    max_compact_attempts: int = 2
    use_default_outputs: bool = True
    result_timeout_s: float = 3600.0
    invoke_backoff_base_s: float = 15.0
    invoke_backoff_cap_s: float = 300.0
    watchdog_grace_s: float = 120.0
    idle_timeout_s: float = 0.0
    cap_default_wait_s: float = 3600.0
    cap_wait_margin_s: float = 120.0
    cap_tick_s: float = 600.0
    max_cap_waits: int = 48
    cap_max_wait_s: float = float(8 * 24 * 3600)

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
        )

    def with_overrides(self, **kwargs: Any) -> AgentResilience:
        """A copy with some fields replaced — used by the test harness to zero the
        recovery sleeps (e.g. ``max_rephrase_attempts=0``) without env mutation."""
        return replace(self, **kwargs)


# Progress-metered loop-guard default (see main.py `_GasTank`); mirrors the old
# module constant so `WORKHORSE_GAS` behaves identically.
_DEFAULT_GAS = 5000


@dataclass(frozen=True)
class RunConfig:
    """Immutable configuration for one engine run.

    Built once by :meth:`from_env` (the CLI boundary in ``main()``), then read by
    the ``Workhorse`` engine instead of ``os.environ``. Tests construct it directly
    with a ``backend_factory`` (a mock backend) and a ``script_runner`` (the
    in-process runner) to drive the engine hermetically.
    """

    resilience: AgentResilience = field(default_factory=AgentResilience)
    #: Loop-guard tank size (WORKHORSE_GAS); 0 disables the guard.
    gas: int = _DEFAULT_GAS
    #: Absolute wall-clock ceiling in seconds (WORKHORSE_MAX_RUNTIME_S); 0 = unbounded.
    max_runtime_s: float = 0.0
    #: Resolves the active agent backend by name. Overridden by the test harness to
    #: return a mock backend; ``None`` means "use runner.backends.get_backend".
    backend_factory: Callable[[str | None], AgentBackend] | None = None
    #: Executes a script node. ``None`` means the default subprocess runner; the test
    #: harness supplies an in-process runner so scriptutil calls are monkeypatchable.
    script_runner: ScriptRunner | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RunConfig:
        e = os.environ if environ is None else environ
        return cls(
            resilience=AgentResilience.from_env(e),
            gas=_configured_gas(e),
            max_runtime_s=_configured_max_runtime_s(e),
        )

    def get_backend(self, cli: str | None = None) -> AgentBackend:
        """Resolve the backend for this run via ``backend_factory`` or the default."""
        if self.backend_factory is not None:
            return self.backend_factory(cli)
        from .runner.backends import get_backend

        return get_backend()

    def get_script_runner(self) -> ScriptRunner:
        if self.script_runner is not None:
            return self.script_runner
        from .runner.script import SubprocessScriptRunner

        return SubprocessScriptRunner()


def _configured_gas(environ: Mapping[str, str]) -> int:
    raw = (environ.get("WORKHORSE_GAS") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return _DEFAULT_GAS


def _configured_max_runtime_s(environ: Mapping[str, str]) -> float:
    raw = (environ.get("WORKHORSE_MAX_RUNTIME_S") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0
