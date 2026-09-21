"""Immutable per-run configuration for the workhorse driver."""

from __future__ import annotations

import os
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from workhorse.runner import transcript
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.null import NullBackend


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


def _positive_int(environ: Mapping[str, str], key: str, default: int) -> int:
    """Like ``_int``, but a zero or negative reading falls back to the default."""
    value = _int(environ, key, default)
    return value if value > 0 else default


def _positive_float(environ: Mapping[str, str], key: str, default: float) -> float:
    """Like ``_float``, with the same "zero is a typo, not a setting" reading."""
    value = _float(environ, key, default)
    return value if math.isfinite(value) and value > 0 else default


def _nonnegative_float(environ: Mapping[str, str], key: str, default: float) -> float:
    """A finite duration where zero explicitly disables waiting."""
    value = _float(environ, key, default)
    return value if math.isfinite(value) and value >= 0 else default


def _bool(environ: Mapping[str, str], key: str, default: bool) -> bool:
    raw = (environ.get(key) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no")


@dataclass(frozen=True)
class AgentResilience:
    """The agent-node recovery ladder's tuning knobs (see runner/ladder.py)."""

    max_output_retries: int = 2
    max_invoke_retries: int = 60
    max_rephrase_attempts: int = 3
    max_compact_attempts: int = 2
    result_timeout_s: float = 3600.0
    invoke_backoff_base_s: float = 15.0
    invoke_backoff_cap_s: float = 1800.0
    retry_wait_budget_s: float = 97305.0
    watchdog_grace_s: float = 120.0
    cap_default_wait_s: float = 600.0
    cap_wait_margin_s: float = 120.0
    cap_tick_s: float = 600.0
    cap_probe_s: float = 7200.0
    max_cap_waits: int = 1536
    cap_max_wait_s: float = float(8 * 24 * 3600)
    cap_wait_budget_s: float = float(8 * 24 * 3600 + 120)
    reframe_wait_budget_s: float = 60.0
    exec_retry_max: int = 5
    exec_retry_base_s: float = 1.0
    exec_retry_cap_s: float = 8.0
    exec_retry_wait_budget_s: float = 23.0
    heartbeat_every_s: float = 10.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AgentResilience:
        e = os.environ if environ is None else environ
        return cls(
            max_output_retries=_int(e, "AGENT_MAX_OUTPUT_RETRIES", 2),
            max_invoke_retries=_int(e, "AGENT_MAX_INVOKE_RETRIES", 60),
            max_rephrase_attempts=_int(e, "AGENT_MAX_REPHRASE_ATTEMPTS", 3),
            max_compact_attempts=_int(e, "AGENT_MAX_COMPACT_ATTEMPTS", 2),
            result_timeout_s=_float(e, "AGENT_RESULT_TIMEOUT_S", 3600.0),
            invoke_backoff_base_s=_nonnegative_float(e, "AGENT_INVOKE_BACKOFF_BASE_S", 15.0),
            invoke_backoff_cap_s=_nonnegative_float(e, "AGENT_INVOKE_BACKOFF_CAP_S", 1800.0),
            retry_wait_budget_s=_nonnegative_float(e, "AGENT_RETRY_WAIT_BUDGET_S", 97305.0),
            watchdog_grace_s=_float(e, "AGENT_WATCHDOG_GRACE_S", 120.0),
            cap_default_wait_s=_nonnegative_float(e, "AGENT_CAP_DEFAULT_WAIT_S", 600.0),
            cap_wait_margin_s=_nonnegative_float(e, "AGENT_CAP_WAIT_MARGIN_S", 120.0),
            cap_tick_s=_positive_float(e, "AGENT_CAP_TICK_S", 600.0),
            cap_probe_s=_nonnegative_float(e, "AGENT_CAP_PROBE_S", 7200.0),
            max_cap_waits=_int(e, "AGENT_MAX_CAP_WAITS", 1536),
            cap_max_wait_s=_nonnegative_float(
                e, "AGENT_CAP_MAX_WAIT_S", float(8 * 24 * 3600)
            ),
            cap_wait_budget_s=_nonnegative_float(
                e, "AGENT_CAP_WAIT_BUDGET_S", float(8 * 24 * 3600 + 120)
            ),
            reframe_wait_budget_s=_nonnegative_float(
                e, "AGENT_REFRAME_WAIT_BUDGET_S", 60.0
            ),
            exec_retry_max=_int(e, "AGENT_EXEC_RETRY_MAX", 5),
            exec_retry_base_s=_nonnegative_float(e, "AGENT_EXEC_RETRY_BASE_S", 1.0),
            exec_retry_cap_s=_nonnegative_float(e, "AGENT_EXEC_RETRY_CAP_S", 8.0),
            exec_retry_wait_budget_s=_nonnegative_float(
                e, "AGENT_EXEC_RETRY_WAIT_BUDGET_S", 23.0
            ),
            heartbeat_every_s=_positive_float(e, "WORKHORSE_OTEL_HEARTBEAT_S", 10.0),
        )

    def with_overrides(self, **kwargs: Any) -> AgentResilience:
        """A copy with some fields replaced — used by the test harness to zero the recovery sleeps (e.g."""
        return replace(self, **kwargs)


@dataclass(frozen=True)
class RunConfig:
    """Immutable configuration for one run."""

    resilience: AgentResilience = field(default_factory=AgentResilience)
    max_runtime_s: float = 0.0
    await_poll_s: float = 15.0
    max_transitions: int = 1000
    print_prompt: bool = True
    model_override: str | None = None
    backend: AgentBackend = field(default_factory=NullBackend)
    profile: str = ""
    workspace: str = ""
    capture_transcripts: bool = True
    transcript_max_bytes: int = transcript.DEFAULT_MAX_BYTES

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RunConfig:
        e = os.environ if environ is None else environ
        return cls(
            resilience=AgentResilience.from_env(e),
            max_runtime_s=_configured_max_runtime_s(e),
            await_poll_s=_positive_float(e, "WORKHORSE_AWAIT_POLL_S", 15.0),
            max_transitions=_positive_int(e, "WORKHORSE_MAX_TRANSITIONS", 1000),
            print_prompt=_bool(e, "WORKHORSE_PRINT_PROMPT", True),
            model_override=(e.get("AGENT_MODEL") or e.get("AGENT_CLAUDE_MODEL") or None),
            workspace=(e.get("AGENT_REPO_DIR") or ""),
            capture_transcripts=_bool(e, "WORKHORSE_CAPTURE_TRANSCRIPTS", True),
            transcript_max_bytes=_positive_int(
                e, "WORKHORSE_TRANSCRIPT_MAX_BYTES", transcript.DEFAULT_MAX_BYTES
            ),
        )


def _configured_max_runtime_s(environ: Mapping[str, str]) -> float:
    raw = (environ.get("WORKHORSE_MAX_RUNTIME_S") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0
