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
    """Like ``_int``, but a zero or negative reading falls back to the default.

    A budget of zero is not "no budget", it is a run that ends before its first
    transition — so a mistyped variable degrades to the shipped default rather than
    to a guard that fires immediately.
    """
    value = _int(environ, key, default)
    return value if value > 0 else default


def _positive_float(environ: Mapping[str, str], key: str, default: float) -> float:
    """Like ``_float``, with the same "zero is a typo, not a setting" reading.

    A poll interval of zero is a busy loop; the default is the safer misread.
    """
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
    """The agent-node recovery ladder's tuning knobs (see runner/ladder.py).

    One field per ``AGENT_*`` env var. Built by :meth:`from_env` at the CLI
    boundary and held as a field of the :class:`~workhorse.runner.ladder.AgentRunner`
    the run is given, so the reframe/retry/cap behavior is set explicitly rather than
    by import-time module constants — which is what lets an in-process test state a
    one-attempt budget without touching the environment.
    """

    #: Additional attempts when Claude's response can't be parsed into the node's
    #: declared outputs.
    max_output_retries: int = 2
    #: Additional attempts when the agent-CLI call itself fails for a *transient*
    #: reason (rate limit, overload, network blip). Each retry waits
    #: min(base * 2**attempt, cap) seconds.
    #:
    #: This budget is sized in DAYS, not minutes, because the failure it covers is
    #: measured in days: a home or office link can be down for a working day, and an
    #: overloaded provider for hours. With the defaults below the ladder climbs
    #: 15s→30m and then holds there, spanning ~27h before it gives up — so an
    #: unattended run sleeps through an outage and resumes on the other side of it
    #: instead of ending inside it. Nothing is consumed while waiting and the run
    #: keeps its checkpoint, so a long wait costs only wall clock.
    max_invoke_retries: int = 60
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
    #: Default per-node wall-clock budget for a single agent turn when the node does
    #: not set its own ``timeout`` (seconds). 1h is long enough for a heavy QA /
    #: build / browser node, short enough that a wedged turn is force-killed and
    #: retried within the hour. Nodes may override per-node (incl. ``infinity``).
    result_timeout_s: float = 3600.0
    invoke_backoff_base_s: float = 15.0
    #: Ceiling on a single transient backoff. Half an hour is the coarsest useful
    #: poll for "is the network back": long enough that a day-long outage costs ~48
    #: probes rather than thousands, short enough that the run restarts within half
    #: an hour of the link returning.
    invoke_backoff_cap_s: float = 1800.0
    #: Cumulative transient-backoff sleep allowed within one agent-node visit.
    retry_wait_budget_s: float = 97305.0
    #: Hard backstop for the per-node timeout. The in-loop ``elapsed > timeout``
    #: check can only fire BETWEEN reads — if the agent writes a partial line and
    #: then its socket wedges (a stalled API stream, a hung MCP server), the reader
    #: blocks inside readline() and the wall-clock check never runs again. A watchdog
    #: on a SEPARATE thread SIGKILLs the whole process group once the turn overruns
    #: its budget by this grace, regardless of stream state.
    watchdog_grace_s: float = 120.0
    cap_default_wait_s: float = 3600.0
    cap_wait_margin_s: float = 120.0
    cap_tick_s: float = 600.0
    max_cap_waits: int = 48
    cap_max_wait_s: float = float(8 * 24 * 3600)
    #: Cumulative cap sleep per node: one maximum structured reset plus its margin.
    cap_wait_budget_s: float = float(8 * 24 * 3600 + 120)
    #: Cumulative pause before fresh-session prompt reframes (10s + 20s + 30s).
    reframe_wait_budget_s: float = 60.0
    #: The agent CLI can be replaced ON DISK mid-run — Claude Code ships a native
    #: binary and self-updates by default, and a manual ``npm i -g`` does the same.
    #: While that in-place rewrite is in flight, exec of the very same path fails for
    #: a sub-second window (ETXTBSY / ENOENT during the rename / ENOEXEC on a
    #: half-written header). That is NOT a missing tool, so a few short retries ride
    #: the update out instead of crashing an otherwise-healthy turn.
    exec_retry_max: int = 5
    exec_retry_base_s: float = 1.0
    exec_retry_cap_s: float = 8.0
    #: Cumulative self-update exec backoff per node (1s + 2s + 4s + 8s + 8s).
    exec_retry_wait_budget_s: float = 23.0
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
            max_invoke_retries=_int(e, "AGENT_MAX_INVOKE_RETRIES", 60),
            max_rephrase_attempts=_int(e, "AGENT_MAX_REPHRASE_ATTEMPTS", 3),
            max_compact_attempts=_int(e, "AGENT_MAX_COMPACT_ATTEMPTS", 2),
            result_timeout_s=_float(e, "AGENT_RESULT_TIMEOUT_S", 3600.0),
            invoke_backoff_base_s=_nonnegative_float(e, "AGENT_INVOKE_BACKOFF_BASE_S", 15.0),
            invoke_backoff_cap_s=_nonnegative_float(e, "AGENT_INVOKE_BACKOFF_CAP_S", 1800.0),
            retry_wait_budget_s=_nonnegative_float(e, "AGENT_RETRY_WAIT_BUDGET_S", 97305.0),
            watchdog_grace_s=_float(e, "AGENT_WATCHDOG_GRACE_S", 120.0),
            cap_default_wait_s=_nonnegative_float(e, "AGENT_CAP_DEFAULT_WAIT_S", 3600.0),
            cap_wait_margin_s=_nonnegative_float(e, "AGENT_CAP_WAIT_MARGIN_S", 120.0),
            cap_tick_s=_positive_float(e, "AGENT_CAP_TICK_S", 600.0),
            max_cap_waits=_int(e, "AGENT_MAX_CAP_WAITS", 48),
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
        """A copy with some fields replaced — used by the test harness to zero the
        recovery sleeps (e.g. ``max_rephrase_attempts=0``) without env mutation."""
        return replace(self, **kwargs)


@dataclass(frozen=True)
class RunConfig:
    """Immutable configuration for one run.

    Built once by :meth:`from_env` (the CLI boundary in ``main()``), then read by the
    driver instead of ``os.environ``. Tests construct it directly — with a fake
    ``backend``, or with the null one the default supplies — to drive a workflow
    hermetically.

    The backend is a *field* rather than something this class *resolves*. Resolving
    one means importing the registry, which imports every adapter, and every adapter
    imports this module for :class:`AgentResilience` — a real cycle, which used to be
    hidden inside a method-body import. Being handed the adapter breaks it: the CLI
    already had to name and validate the backend, so it is the ring that owns the
    choice, and nothing here needs to know a *selectable* adapter exists. The one
    adapter named here is the null one, which no operator can select and which
    imports nothing beyond the port.
    """

    resilience: AgentResilience = field(default_factory=AgentResilience)
    #: Absolute wall-clock ceiling in seconds (WORKHORSE_MAX_RUNTIME_S); 0 = unbounded.
    max_runtime_s: float = 0.0
    #: How often an ``Await`` re-stats the file it is blocked on
    #: (WORKHORSE_AWAIT_POLL_S). The wait is measured in days, so this is about not
    #: spinning rather than about latency.
    await_poll_s: float = 15.0
    #: Transitions a run may make before it is declared stuck
    #: (WORKHORSE_MAX_TRANSITIONS). The gas tank bounds node *work*; this bounds the
    #: state machine itself, so a two-state ping-pong that burns no gas still ends. A
    #: workflow class that sets ``max_transitions`` overrides this for its own runs.
    max_transitions: int = 1000
    #: Echo the path of each node's rendered prompt to the console
    #: (WORKHORSE_PRINT_PROMPT); the path only, never the rendered variables.
    print_prompt: bool = True
    #: Run-level model override (AGENT_MODEL, else AGENT_CLAUDE_MODEL), used when the
    #: node's power tier maps to no model. None = no override, so the backend's
    #: ``[default.<backend>]`` entry and then its built-in decide.
    model_override: str | None = None
    #: The agent CLI this run drives, already resolved. The CLI boundary picks it —
    #: ``--cli`` else ``AGENT_CLI`` — and validates it there, so an unknown name fails
    #: before the first state rather than at the first agent node. A run with no agent
    #: in it — a dry run, or a test driving script nodes only — gets the
    #: :class:`~workhorse.runner.backends.null.NullBackend`, never ``None``: absence is
    #: an implementation of the port, so nothing downstream branches on it and
    #: ``AgentRunner.backend`` can honestly claim to hold an ``AgentBackend``.
    backend: AgentBackend = field(default_factory=NullBackend)
    #: The named model set this run resolves its models from (``--profile``), or "" for
    #: the config's top-level tables. Like ``backend``, it comes from the flag rather
    #: than from :meth:`from_env`: it is a run policy the CLI boundary decides and
    #: validates, not an environment reading. What it selects is re-read per turn, so
    #: editing the profile mid-run still moves the run — only the *name* is fixed here.
    profile: str = ""
    #: The working tree this run operates on (AGENT_REPO_DIR), or "" for the process
    #: cwd. Only a path — the driver makes no claim that it is a repository, and
    #: :mod:`workhorse.gitstate` observes it rather than assuming. Read here for the
    #: same reason as everything else in this class: so the driver never asks the
    #: environment a second time and gets a different answer.
    workspace: str = ""
    #: Keep each agent turn's transcript under the run's ``transcripts/``
    #: (WORKHORSE_CAPTURE_TRANSCRIPTS). On by default: what it buys — being able to see
    #: why a node re-decided the same thing five times — is only available after the
    #: fact, so a run that has to be told to record is a run that never recorded the
    #: turn anyone ends up asking about.
    capture_transcripts: bool = True
    #: Per-turn ceiling on a captured transcript, in bytes
    #: (WORKHORSE_TRANSCRIPT_MAX_BYTES). A turn runs 0.5-1.1 MB; the default is sized
    #: for the pathological turn, and a capture that hits it is truncated with a marker
    #: line rather than dropped.
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
