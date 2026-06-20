from __future__ import annotations
import json
import os
import re
import select
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..graph.nodes import AgentNode

if TYPE_CHECKING:
    from .backends import AgentBackend
from ..graph.context import WorkflowContext
from ..templates import render, render_string


# Active subprocess registry — lets the top-level interrupt handler terminate
# the currently-streaming Claude process cleanly instead of leaving it orphaned.
_active_proc_lock: threading.Lock = threading.Lock()
_active_proc: subprocess.Popen | None = None


def terminate_active() -> None:
    """Terminate the currently-streaming Claude subprocess, if any.

    Called by the main loop's KeyboardInterrupt handler so the child process is
    cleaned up before workhorse exits, rather than being left as an orphan.
    """
    with _active_proc_lock:
        proc = _active_proc
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# Number of additional attempts when Claude's response can't be parsed into the
# node's declared outputs. Overridable via env for ops without a code change.
DEFAULT_MAX_OUTPUT_RETRIES = int(os.environ.get("AGENT_MAX_OUTPUT_RETRIES", "2"))

# Number of additional attempts when the Claude CLI call itself fails for a
# *transient* reason (spending cap, rate limit, overload, network blip). Each
# retry waits min(base * 2**attempt, cap) seconds. All overridable via env.
DEFAULT_MAX_INVOKE_RETRIES = int(os.environ.get("AGENT_MAX_INVOKE_RETRIES", "4"))

# When invocation + output parsing still fail after the transient retries above,
# REFRAME the prompt from scratch in a fresh session and try the node again, up
# to this many times. This is the second resilience layer for unattended runs:
# a node Claude can't answer as-phrased often succeeds when re-asked more simply.
DEFAULT_MAX_REPHRASE_ATTEMPTS = int(os.environ.get("AGENT_MAX_REPHRASE_ATTEMPTS", "3"))

# When a node's run exhausts the model's context window and the headless CLI
# returns instead of auto-compacting, the runner first tries to COMPACT the
# session and continue (preserving the node's progress) this many times before
# falling through to the generic reframe ladder. Compaction reuses the same
# session, so it keeps what the node has done so far; reframing would throw it
# away. 0 disables compaction recovery (straight to reframe).
DEFAULT_MAX_COMPACT_ATTEMPTS = int(os.environ.get("AGENT_MAX_COMPACT_ATTEMPTS", "2"))

# Final resilience layer: when every reframing fails, return safe default outputs
# so the controller advances to the node's `next` instead of crashing the run.
# This worker is built to run autonomously for days — a single unanswerable node
# must degrade to "continue" rather than abort the whole program. Disable
# (AGENT_USE_DEFAULT_OUTPUTS=false) only when a hard stop on failure is wanted.
USE_DEFAULT_OUTPUTS = os.environ.get("AGENT_USE_DEFAULT_OUTPUTS", "true").lower() == "true"

# Maximum time to wait for a result event from Claude (in seconds)
DEFAULT_RESULT_TIMEOUT_S = float(os.environ.get("AGENT_RESULT_TIMEOUT_S", "600"))
_INVOKE_BACKOFF_BASE_S = float(os.environ.get("AGENT_INVOKE_BACKOFF_BASE_S", "15"))
_INVOKE_BACKOFF_CAP_S = float(os.environ.get("AGENT_INVOKE_BACKOFF_CAP_S", "300"))

# A subscription "cap" is a transient failure that recovers on a SCHEDULE — the
# spending/usage/session window resets at a wall-clock time (e.g. "resets 3:50am",
# "session limit · resets 11:30am"), not after a few seconds. We wait it out until
# the reset rather than burning the short-backoff budget above (and never reframe
# the prompt — re-asking a capped subscription can't help). This is baked into the
# core agent so a single run survives a cap with no supervisor — and because an AI
# "fixer" can't help here anyway: it would run on the same capped subscription.
_CAP_MARKERS = ("spending cap", "usage limit", "weekly limit", "session limit", "quota")
# Fallback wait when the reset time can't be parsed from the message, then re-probe.
_CAP_DEFAULT_WAIT_S = float(os.environ.get("AGENT_CAP_DEFAULT_WAIT_S", "3600"))
# Added after a parsed reset so we wake just AFTER the window reopens.
_CAP_WAIT_MARGIN_S = float(os.environ.get("AGENT_CAP_WAIT_MARGIN_S", "120"))
# Emit a "still paused" line every this many seconds so a long wait isn't mistaken
# for a hang.
_CAP_TICK_S = float(os.environ.get("AGENT_CAP_TICK_S", "600"))
# Safety bound on consecutive cap waits (each up to ~a day) before giving up.
_MAX_CAP_WAITS = int(os.environ.get("AGENT_MAX_CAP_WAITS", "48"))
# Upper bound on a single structured (resetsAt-derived) cap sleep. A genuine
# weekly reset is ~7 days, so the default leaves headroom; anything larger is
# treated as bogus and we re-probe sooner instead of sleeping for it.
_CAP_MAX_STRUCTURED_WAIT_S = float(os.environ.get("AGENT_CAP_MAX_WAIT_S", str(8 * 24 * 3600)))
# Substrings (case-insensitive) in a rate_limit_event's status that mark the limit
# as actually HIT (vs the normal "allowed"). Conservative on purpose: an unknown
# benign status must not be mistaken for a cap. Text markers remain the primary
# cap detector; this is an additional structured signal.
_LIMIT_STATUS_MARKERS = (
    "block", "reject", "exceed", "throttl", "reached", "denied", "over_limit", "limit_reached",
)

# Substrings (case-insensitive) in the CLI's output that mark a retryable,
# non-deterministic failure. Anything else fails fast — retrying a deterministic
# error just burns time and tokens.
_TRANSIENT_MARKERS = (
    "spending cap",
    "usage limit",
    "weekly limit",
    "session limit",
    "quota",
    "rate limit",
    "rate-limit",
    "overloaded",
    "capacity",
    "temporarily unavailable",
    "service unavailable",
    "internal server error",
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection reset",
    "connection error",
    "econnreset",
    "etimedout",
    "network",
)

# Substrings (case-insensitive) that mark an exhausted context window — the model
# ran out of room mid-node and the headless CLI returned without compacting. This
# is NOT a generic transient (retrying the same overflows again) and NOT a cap;
# the runner recovers it by compacting the session and continuing.
_CONTEXT_OVERFLOW_MARKERS = (
    "prompt is too long",
    "input is too long",
    "context length",
    "context window",
    "maximum context",
    "context limit",
    "exceeds the maximum",
    "too many tokens",
    "conversation is too long",
)


class OutputParseError(RuntimeError):
    """Claude's response could not be parsed into the node's declared outputs.

    Distinct from generic RuntimeError so the runner only retries this failure
    mode (a recoverable, re-promptable mistake) and not e.g. a CLI crash.
    """


class BackendInvocationError(RuntimeError):
    """An agent-CLI turn failed (non-zero exit, or no result event).

    ``transient`` flags failures worth retrying with backoff (spending cap,
    rate limit, overload, network) versus deterministic ones that should fail
    fast. ``overflow`` flags the special case where the model's context window
    was exhausted mid-node and the headless CLI returned instead of compacting —
    the runner recovers this by compacting the session and continuing (see
    ``run_agent``), so it is NOT retried with backoff (that would just overflow
    again) and is handled before the generic reframe ladder.
    """

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        overflow: bool = False,
        timed_out: bool = False,
        reset_at: float | None = None,
    ) -> None:
        super().__init__(message)
        self.transient = transient
        self.overflow = overflow
        # The turn was killed for exceeding its wall-clock budget (not a rate
        # limit / network blip). The retry loop uses this to warn the next attempt
        # that it overran, and by how much, so it can size its work to fit.
        self.timed_out = timed_out
        # Unix epoch (seconds) when the capped window reopens, taken from the CLI's
        # structured ``rate_limit_event`` (``rate_limit_info.resetsAt``). Set only
        # on cap-like failures so a normal transient never looks like a cap; the
        # runner sleeps until this instant when present (more precise than parsing
        # "resets 11:30am" out of the message).
        self.reset_at = reset_at


# Backwards-compatible alias: this error was originally Claude-specific, but the
# resilience ladder and backends are now CLI-agnostic. main.py and tests import
# the old name; keep it pointing at the same class.
ClaudeInvocationError = BackendInvocationError


def _print_rendered_prompt(node_id: str, prompt: str) -> None:
    """Echo the fully-rendered prompt to stdout, framed so it's easy to spot in the log."""
    print(f"[{node_id}] ┌─ rendered prompt ({len(prompt)} chars) " + "─" * 24, flush=True)
    print(prompt, flush=True)
    print(f"[{node_id}] └─ end prompt " + "─" * 34, flush=True)


def _model_for_backend(node_model: "str | dict[str, str] | None", backend_name: str) -> str | None:
    """Resolve a node's ``model:`` field for the active CLI backend.

    - ``None``  → no per-node model (caller falls through to env / backend default).
    - ``str``   → an absolute default applied to every backend (existing behaviour).
    - ``dict``  → per-CLI map keyed by backend name ("claude"/"codex"/"copilot");
                  an optional ``"default"`` key covers any backend not listed. A
                  backend that is neither listed nor has a ``"default"`` yields
                  ``None`` so the caller falls through to AGENT_MODEL / the backend
                  default — i.e. the map only pins the backends it names.
    """
    if node_model is None:
        return None
    if isinstance(node_model, str):
        return node_model
    return node_model.get(backend_name) or node_model.get("default")


def _resolve_model(
    node_model: "str | dict[str, str] | None",
    backend_name: str,
    environ: "dict[str, str]",
) -> str | None:
    """Concrete model for this node: the node's per-CLI ``model:`` map
    (``_model_for_backend``), then ``AGENT_MODEL`` / ``AGENT_CLAUDE_MODEL``.
    ``None`` lets the caller fall back to ``backend.default_model``.

    A node targets an OpenRouter model by keying its ``model:`` map on the backend
    that speaks OpenRouter, e.g. ``{aider: openrouter/xiaomi/mimo-v2.5}`` run with
    ``--cli aider`` — no proxy, no run-level profile."""
    return (
        _model_for_backend(node_model, backend_name)
        or environ.get("AGENT_MODEL")
        or environ.get("AGENT_CLAUDE_MODEL")
    )


def run_agent(
    node: AgentNode,
    context: WorkflowContext,
    workflow_dir: Path,
    session_id_path: Path | None = None,
    max_output_retries: int = DEFAULT_MAX_OUTPUT_RETRIES,
    max_rephrase_attempts: int = DEFAULT_MAX_REPHRASE_ATTEMPTS,
    max_compact_attempts: int = DEFAULT_MAX_COMPACT_ATTEMPTS,
    resume_session: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Render the prompt, invoke Claude, and parse its declared outputs — resiliently.

    This worker is built to run unattended for days, so one bad node must never
    crash the whole run. Recovery escalates through four layers:

    1. **Transient retries** (inside ``_invoke_claude``): rate limits, overloads,
       network blips, timeouts, *empty* results and spending caps are retried or
       waited out with backoff.
    2. **Compact & continue** (here): if the node exhausts the model's context
       window (the headless CLI returns instead of auto-compacting), the session
       is compacted and the node retried on it — preserving the node's progress —
       up to ``max_compact_attempts`` times before reframing.
    3. **Reframe** (here): if invocation or output parsing still fails, the prompt
       is rephrased from scratch in a fresh session and the node is retried, up to
       ``max_rephrase_attempts`` times. A node Claude can't answer as-phrased
       often succeeds when re-asked more simply.
    4. **Default to next** (here): when every reframing fails, return safe default
       outputs so the controller advances to ``node.next`` instead of aborting.
       Set ``AGENT_USE_DEFAULT_OUTPUTS=false`` to hard-fail instead.

    **Sessions.** Each node is a fresh prompt and starts from a *clean context* —
    we do NOT chain one node's conversation into the next. The persisted Claude
    session is resumed only when ``resume_session`` is True, which the controller
    sets solely to continue *this same node* after an interruption (a crash mid
    node). A normal forward move to a new node always starts clean. (The
    compact-and-continue layer above also resumes the session, but only within
    this same call, to recover the node it is already running.)

    Returns (rendered_prompt, extracted_outputs_dict).
    """
    ctx = context.as_dict()

    # The wall-clock budget for this node's turn: the node's own timeout when set,
    # else the engine default. Surfaced to the prompt (node_timeout_s/min) so the
    # agent can size its commands to finish — a turn killed at the budget restarts
    # the node from scratch with no memory, wasting the whole budget.
    effective_timeout = node.timeout if node.timeout else DEFAULT_RESULT_TIMEOUT_S
    # An unbounded budget (timeout: infinity) means "never kill this turn". The stream
    # loops compare `elapsed > timeout`, so float('inf') naturally never trips; only the
    # prompt-surfaced ints need a non-numeric stand-in (int(inf) would overflow).
    unbounded = effective_timeout == float("inf")

    # Render node args as Jinja2 strings, merge into context for prompt rendering
    rendered_args = {k: render_string(v, ctx) for k, v in node.args.items()}
    prompt_ctx = {
        **ctx,
        **rendered_args,
        "node_timeout_s": "unbounded" if unbounded else int(effective_timeout),
        "node_timeout_min": "unbounded" if unbounded else int(round(effective_timeout / 60)),
    }
    rendered_prompt = render(node.prompt, prompt_ctx, workflow_dir)

    # Echo the fully-rendered prompt before launching the agent. Library prompts now
    # render dynamically from the context manifest + live run context, so seeing the
    # exact text (resolved instruction paths, per-layer run plan, gated sections) is
    # the fastest way to catch a mis-resolved variable. On (default); WORKHORSE_PRINT_PROMPT=0
    # silences it. The prompt is also persisted to the run dir's prompt.md afterward.
    if os.environ.get("WORKHORSE_PRINT_PROMPT", "1").lower() not in ("0", "false", "no", ""):
        _print_rendered_prompt(node.id, rendered_prompt)

    # Render per-node working directory and additional directories from context.
    rendered_cwd = render_string(node.cwd, ctx).strip() if node.cwd else None
    rendered_add_dirs = [
        d for d in (render_string(d, ctx).strip() for d in node.add_dirs) if d
    ]

    # Resolve the active CLI backend for this run (per-run via AGENT_CLI; default
    # claude). Imported lazily to avoid an import cycle (backends imports this
    # module). Used here for the compaction step and the per-backend model default.
    from .backends import get_backend
    backend = get_backend()

    # The model comes from the node's per-CLI `model:` map → AGENT_MODEL /
    # AGENT_CLAUDE_MODEL → backend default. See _resolve_model.
    model = _resolve_model(node.model, backend.name, os.environ) or backend.default_model

    # Reasoning/thinking effort is per-node (a model that isn't a reasoning model
    # simply leaves it unset in the workflow).
    node_effort = node.effort

    # New node = clean context: drop any session left by a previous node so this
    # node's first attempt does not --resume someone else's conversation. When
    # resume_session is set we keep it, so the interrupted node continues where it
    # left off (the controller only asks for this on the re-entered node).
    if not resume_session and session_id_path and session_id_path.exists():
        session_id_path.unlink()

    # ``rephrase`` advances only on a genuine reframe; a context-compaction retry
    # re-runs the SAME prompt on the compacted session without consuming a reframe.
    rephrase = 0
    compact_attempts = max_compact_attempts
    while True:
        prompt = (
            rendered_prompt
            if rephrase == 0
            else _rephrase_prompt(rendered_prompt, node, rephrase)
        )
        # A reframed attempt starts a FRESH session so the prior, unhelpful
        # exchange doesn't bias the model toward repeating its mistake.
        if rephrase > 0:
            if session_id_path and session_id_path.exists():
                session_id_path.unlink()
            print(
                f"[{node.id}] 🔄 reframing prompt "
                f"(attempt {rephrase}/{max_rephrase_attempts})",
                flush=True,
            )
        try:
            outputs = _invoke_and_parse(
                prompt, node, session_id_path, model, max_output_retries,
                timeout=effective_timeout,
                cwd=rendered_cwd, add_dirs=rendered_add_dirs,
                effort=node_effort,
            )
            return rendered_prompt, outputs
        except (ClaudeInvocationError, OutputParseError) as exc:
            # Layer 2: context window exhausted → compact this session and retry the
            # SAME prompt on it, keeping the node's progress. Only when compaction
            # is unavailable/ineffective do we fall through to a (lossy) reframe.
            if (
                isinstance(exc, BackendInvocationError)
                and exc.overflow
                and backend.supports_compaction
                and compact_attempts > 0
            ):
                compact_attempts -= 1
                attempt_no = max_compact_attempts - compact_attempts
                print(
                    f"[{node.id}] 🗜 context window exhausted; compacting session "
                    f"and continuing (attempt {attempt_no}/{max_compact_attempts})",
                    flush=True,
                )
                if backend.compact(session_id_path, node.id, model):
                    continue  # retry same prompt on the compacted session
                print(
                    f"[{node.id}] ⚠ compaction unavailable/ineffective; "
                    f"falling back to reframe",
                    flush=True,
                )

            # Layer 3: reframe in a fresh session.
            if rephrase < max_rephrase_attempts:
                print(
                    f"[{node.id}] ⚠ node failed ({exc}); will reframe and retry",
                    flush=True,
                )
                # Brief, escalating pause so a reframe doesn't hammer a struggling
                # service back-to-back.
                time.sleep(min(10 * (rephrase + 1), 60))
                rephrase += 1
                continue

            # Layer 4: don't crash an unattended run on one unanswerable node.
            if USE_DEFAULT_OUTPUTS:
                print(
                    f"[{node.id}] ⏭ all {max_rephrase_attempts} reframings failed "
                    f"({exc}); using default outputs to advance to the next node",
                    flush=True,
                )
                return rendered_prompt, _default_outputs(node)
            raise


def _invoke_and_parse(
    prompt: str,
    node: AgentNode,
    session_id_path: Path | None,
    model: str | None,
    max_output_retries: int,
    timeout: float = DEFAULT_RESULT_TIMEOUT_S,
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
    effort: str | None = None,
) -> dict[str, Any]:
    """Invoke Claude and parse the node's declared outputs.

    When the response can't be parsed into the declared outputs, re-prompt within
    the SAME session up to ``max_output_retries`` times with a corrective message
    before giving up (raising ``OutputParseError`` for the caller's reframe layer).
    """
    for attempt in range(max_output_retries + 1):
        result_text = _invoke_claude(
            prompt, node.id, session_id_path, model=model, timeout=timeout,
            cwd=cwd, add_dirs=add_dirs, effort=effort,
        )
        try:
            return _extract_outputs(result_text, node)
        except OutputParseError as exc:
            if attempt >= max_output_retries:
                raise
            print(
                f"[{node.id}] ⚠ output parse failed "
                f"(attempt {attempt + 1}/{max_output_retries + 1}): {exc}; retrying",
                flush=True,
            )
            # Resume the same session (session id was just persisted) and nudge
            # Claude to emit only the required JSON.
            prompt = _retry_prompt(node, exc)

    # Unreachable: the loop either returns outputs or raises on the final attempt.
    raise AssertionError("_invoke_and_parse retry loop exited without a result")


def _invoke_claude(
    prompt: str,
    node_id: str,
    session_id_path: Path | None,
    model: str | None = None,
    backend: "AgentBackend | None" = None,
    max_invoke_retries: int = DEFAULT_MAX_INVOKE_RETRIES,
    timeout: float = DEFAULT_RESULT_TIMEOUT_S,
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
    effort: str | None = None,
) -> str:
    """Run one agent-CLI turn for ``prompt``, recovering from transient failures.

    Two recovery modes:
    - **Spending/usage cap** — a *scheduled* failure that clears only when the
      subscription window resets. We sleep until that reset (parsed from the
      message, else a default), announcing it on the console, then retry. This is
      NOT bounded by the short-retry budget: a cap always recovers eventually, so
      the run rides it out instead of dying.
    - **Short transient** (rate limit, overload, network) — bounded exponential
      backoff, then fail fast.

    Persists the resulting session id (when available) so a subsequent call
    resumes the same conversation.
    """
    if backend is None:
        from .backends import get_backend
        backend = get_backend()

    short_attempt = 0
    cap_waits = 0
    # The prompt sent on the current attempt. After a budget timeout we prepend a
    # warning (see below) so the retry knows it overran and how long it has.
    attempt_prompt = prompt
    while True:
        try:
            print(f"[{node_id}] 🚀 Invoking {backend.name} (model: {model or 'default'})", flush=True)
            return backend.run_turn(
                attempt_prompt, node_id, session_id_path, model, timeout=timeout,
                cwd=cwd, add_dirs=add_dirs, effort=effort,
            )
        except BackendInvocationError as exc:
            print(f"[{node_id}] ⚠ Claude invocation failed: {exc}", flush=True)
            if not exc.transient:
                raise
            # A budget timeout: warn the next attempt that it overran and give it the
            # wall-clock budget so it can size its work to fit. Other transients
            # (rate limit, overload, network) retry the prompt unchanged.
            if exc.timed_out:
                print(
                    f"[{node_id}] ⏱ previous attempt exceeded its ~{int(timeout)}s "
                    f"budget; warning the retry to size its work to fit",
                    flush=True,
                )
                attempt_prompt = _timeout_retry_prompt(prompt, timeout)
            else:
                attempt_prompt = prompt
            if exc.reset_at is not None or _is_cap(str(exc)):
                if cap_waits >= _MAX_CAP_WAITS:
                    raise
                cap_waits += 1
                delay, when = _cap_delay_seconds(exc)
                print(
                    f"[{node_id}] ⏸ spending/usage cap reached — pausing ~{int(delay)}s "
                    f"(resuming around {when}). The cap clears only when the window "
                    f"resets, so the run sleeps through it. ({str(exc).strip()})",
                    flush=True,
                )
                _sleep_with_notice(delay, node_id, "cap reset")
                print(f"[{node_id}] ▶ cap wait elapsed — resuming node", flush=True)
                continue
            if short_attempt >= max_invoke_retries:
                raise
            delay = min(_INVOKE_BACKOFF_BASE_S * (2 ** short_attempt), _INVOKE_BACKOFF_CAP_S)
            short_attempt += 1
            print(
                f"[{node_id}] ⚠ transient Claude CLI failure "
                f"(attempt {short_attempt}/{max_invoke_retries}): {exc}; "
                f"retrying in {int(delay)}s",
                flush=True,
            )
            time.sleep(delay)


def _run_claude_cli(
    prompt: str,
    node_id: str,
    session_id_path: Path | None,
    model: str | None = None,
    timeout: float = DEFAULT_RESULT_TIMEOUT_S,
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
    effort: str | None = None,
) -> str:
    """Run a single Claude CLI turn for ``prompt``, returning the final result
    text. Raises ``ClaudeInvocationError`` on CLI failure, classifying it as
    transient when the captured output matches a known retryable marker.

    Args:
        timeout: Maximum seconds to wait for a result event from Claude.
        cwd: Working directory for the subprocess (controls CLAUDE.md discovery).
        add_dirs: Additional directories to grant the agent access to.
    """
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])
    for d in (add_dirs or []):
        cmd.extend(["--add-dir", d])
    cmd.append("-p")

    # Resume session if one exists
    if session_id_path and session_id_path.exists():
        sid = session_id_path.read_text().strip()
        if sid:
            cmd.extend(["--resume", sid])
            print(f"[{node_id}] 🔄 Resuming session: {sid[:8]}...", flush=True)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so a full stderr buffer can't deadlock the read
        text=True,
        bufsize=1,
        cwd=cwd or None,
        env={**os.environ, "WORKHORSE_NODE_ID": node_id},
    )
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    global _active_proc
    with _active_proc_lock:
        _active_proc = proc
    try:
        # Stream Claude's events to our stdout as they arrive (so they show up live in
        # the run log) while accumulating the final result text + session id. The
        # diagnostics string captures non-event output (e.g. "Spending cap reached")
        # and error-result subtypes so we can tell transient failures apart.
        result_text, new_session_id, diagnostics, timed_out, rate_limited, rate_reset_at = (
            _stream_events(proc, node_id, timeout)
        )
        proc.wait()
    finally:
        with _active_proc_lock:
            _active_proc = None

    # A cap-like failure (text markers or a blocked rate_limit_event) carries the
    # structured reset epoch so the runner can sleep until the window reopens; a
    # plain transient must NOT, or it would be mistaken for a cap.
    cap_ish = rate_limited or _is_cap(diagnostics)
    cap_reset_at = rate_reset_at if cap_ish else None
    
    # Handle timeout case specially - always transient
    if timed_out:
        # Try to terminate the process gracefully
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        raise ClaudeInvocationError(
            f"Timeout waiting for result from Claude for node '{node_id}' after {timeout}s"
            + (f": {diagnostics.strip()}" if diagnostics.strip() else ""),
            transient=True,
            timed_out=True,
        )

    # Context window exhausted mid-node: the headless CLI returned (often with an
    # error result and/or a non-zero exit) instead of compacting. Detect this
    # before the generic exit-code/empty-result checks, persist the session id so
    # the runner can compact-and-continue THIS session (keeping the node's
    # progress), and surface it as a distinct, non-transient overflow error.
    if _is_context_overflow(diagnostics):
        if session_id_path and new_session_id:
            session_id_path.write_text(new_session_id)
        raise ClaudeInvocationError(
            f"Context window exhausted for node '{node_id}'"
            + (f": {diagnostics.strip()}" if diagnostics.strip() else ""),
            transient=False,
            overflow=True,
        )

    if proc.returncode != 0:
        raise ClaudeInvocationError(
            f"Claude CLI exited with code {proc.returncode} for node '{node_id}'"
            + (f": {diagnostics.strip()}" if diagnostics.strip() else ""),
            transient=_is_transient(diagnostics) or rate_limited,
            reset_at=cap_reset_at,
        )
    if not result_text:
        # No result is often transient - Claude may have been interrupted
        raise ClaudeInvocationError(
            f"No 'result' event received from Claude for node '{node_id}'"
            + (f": {diagnostics.strip()}" if diagnostics.strip() else ""),
            transient=True,  # Changed to True - missing result is often transient
            reset_at=cap_reset_at,
        )

    if session_id_path and new_session_id:
        session_id_path.write_text(new_session_id)

    return result_text


def _compact_session(
    session_id_path: Path | None,
    node_id: str,
    model: str | None = None,
    timeout: float = DEFAULT_RESULT_TIMEOUT_S,
) -> bool:
    """Best-effort: resume the node's session and run the CLI's ``/compact`` command
    to summarize the conversation so far, freeing context so the node can continue
    on the same (now smaller) session.

    Persists the resulting session id so the next attempt resumes the compacted
    conversation. Returns True when compaction ran without itself overflowing;
    returns False (never raises) when there is no session to compact, the call
    fails, or ``/compact`` couldn't run within the window — callers then fall back
    to reframing.

    The headless CLI (verified on Claude Code 2.1.x) honors ``/compact`` in ``-p
    --resume`` mode and reports the outcome via ``system``/``status`` events:
    ``status: "compacting"`` then a terminal event carrying ``compact_result``
    ("success" / "failed", with ``compact_error``). The session id is preserved.
    We key success off ``compact_result`` (treating "started but no explicit
    failure" as success for forward-compat), and persist the session id so the
    retry resumes the compacted conversation.
    """
    if not (session_id_path and session_id_path.exists()):
        return False
    sid = session_id_path.read_text().strip()
    if not sid:
        return False

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["--resume", sid, "-p"])

    print(f"[{node_id}] 🗜 compacting session {sid[:8]}… to free context", flush=True)
    saw_compacting = False
    compact_failed = False
    compact_error = ""
    new_session_id = sid
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdin is not None
        proc.stdin.write("/compact")
        proc.stdin.close()

        start = time.time()
        assert proc.stdout is not None
        while True:
            if time.time() - start > timeout:
                break
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            raw = proc.stdout.readline()
            if not raw:
                break
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("session_id"):
                new_session_id = event["session_id"]
            if event.get("status") == "compacting":
                saw_compacting = True
            if "compact_result" in event:
                if event.get("compact_result") == "failed":
                    compact_failed = True
                    compact_error = str(event.get("compact_error") or "")
                elif event.get("compact_result") == "success":
                    saw_compacting = True
    except Exception as exc:  # noqa: BLE001 — compaction is best-effort
        print(f"[{node_id}] ⚠ compaction call failed: {exc}", flush=True)
        return False
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    if new_session_id:
        session_id_path.write_text(new_session_id)

    if compact_failed:
        print(f"[{node_id}] ⚠ compaction failed: {compact_error}", flush=True)
        return False
    return saw_compacting


def _is_transient(diagnostics: str) -> bool:
    low = diagnostics.lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


def _is_cap(diagnostics: str) -> bool:
    """A scheduled-reset cap (spending/usage/weekly/session/quota), distinct from a
    short transient like a rate limit or overload that clears in seconds."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CAP_MARKERS)


def _is_context_overflow(diagnostics: str) -> bool:
    """The model's context window was exhausted mid-node (the headless CLI returned
    instead of compacting). Recovered by compacting the session, not by retrying."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CONTEXT_OVERFLOW_MARKERS)


def _parse_reset_seconds(text: str, now: datetime | None = None) -> float | None:
    """Seconds from ``now`` until the cap reset time named in ``text`` — e.g.
    'resets 3:50am', 'resets at 11pm', 'resets 15:50'. Returns the next future
    occurrence of that clock time, or None if no time is found (caller defaults)."""
    now = now or datetime.now()
    m = re.search(r"resets?(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)", text, re.IGNORECASE)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == "pm":
            hour += 12
        minute = int(m.group(2) or 0)
    else:
        m = re.search(r"resets?(?:\s+at)?\s+(\d{1,2}):(\d{2})\b", text, re.IGNORECASE)
        if not m:
            return None
        hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _rate_limit_info(event: dict) -> tuple[bool, float | None]:
    """Read a ``rate_limit_event`` → ``(blocked, reset_at_epoch)``.

    ``blocked`` is True when the status names a limit actually being hit (not the
    normal "allowed"). ``reset_at`` is the window's reset time as a unix epoch when
    present (emitted on every event, not just blocked ones). Either may be falsy.
    """
    info = event.get("rate_limit_info") or {}
    status = str(info.get("status") or "").lower()
    blocked = any(marker in status for marker in _LIMIT_STATUS_MARKERS)
    raw_reset = info.get("resetsAt")
    try:
        reset_at = float(raw_reset) if raw_reset is not None else None
    except (TypeError, ValueError):
        reset_at = None
    return blocked, reset_at


def _cap_delay_seconds(exc: ClaudeInvocationError, now: float | None = None) -> tuple[float, str]:
    """How long to sleep for a cap, and a human 'resuming around' label.

    Prefers the structured ``reset_at`` epoch (precise, timezone-correct) when the
    error carries one, bounded by ``_CAP_MAX_STRUCTURED_WAIT_S``; otherwise parses
    a reset time from the message text; otherwise uses the default wait.
    """
    now = now if now is not None else time.time()
    if exc.reset_at is not None:
        secs = exc.reset_at - now
        if secs > 0:
            delay = min(secs, _CAP_MAX_STRUCTURED_WAIT_S) + _CAP_WAIT_MARGIN_S
            when = datetime.fromtimestamp(now + delay).strftime("%a %H:%M")
            return delay, when
        # Reset already passed (stale event / clock skew) → retry promptly.
        return _CAP_WAIT_MARGIN_S, "reset already passed — retrying shortly"

    parsed = _parse_reset_seconds(str(exc))
    if parsed is None:
        return _CAP_DEFAULT_WAIT_S, "unknown reset — using default wait"
    delay = parsed + _CAP_WAIT_MARGIN_S
    return delay, (datetime.now() + timedelta(seconds=delay)).strftime("%a %H:%M")


def _sleep_with_notice(total_s: float, node_id: str, label: str) -> None:
    """Sleep ``total_s`` seconds, printing a 'still paused' line every _CAP_TICK_S
    so a long, legitimate wait can't be mistaken for a hang."""
    remaining = total_s
    while remaining > 0:
        chunk = min(remaining, _CAP_TICK_S)
        time.sleep(chunk)
        remaining -= chunk
        if remaining > 0:
            print(
                f"[{node_id}] ⏸ still paused ({label}); ~{int(remaining)}s remaining",
                flush=True,
            )


def _retry_prompt(node: AgentNode, error: OutputParseError) -> str:
    """Corrective follow-up asking Claude to re-emit only the required outputs."""
    keys = [o.key for o in node.outputs]
    return (
        "Your previous response could not be parsed into this node's required "
        f"outputs.\nError: {error}\n\n"
        "Do not redo any work. Reply with ONLY a single JSON object "
        "(optionally inside a ```json fenced code block) containing exactly "
        f"these keys: {keys}. Include no other commentary before or after it."
    )


def _timeout_retry_prompt(original_prompt: str, timeout: float) -> str:
    """Prepend a budget warning to a prompt whose previous attempt was killed for
    overrunning its wall-clock budget. Tells the retry how long it has so it can
    size its work to finish — and leave margin to emit its result — this time."""
    minutes = max(1, int(round(timeout / 60)))
    notice = (
        "⚠️ TIME BUDGET — your previous attempt at this task was STOPPED for "
        f"exceeding its wall-clock budget of ~{minutes} min ({int(timeout)}s), and "
        "all of its work was lost. You get the SAME ~"
        f"{minutes} min for this attempt. Do NOT run any command that cannot finish "
        "well within that budget: time long operations first, run measurements at a "
        "reduced scale if the full run will not fit, and leave margin to write your "
        "final result before time runs out. Then carry out the task below.\n\n"
    )
    return notice + original_prompt


def _rephrase_prompt(original_prompt: str, node: AgentNode, attempt: int) -> str:
    """Reframe the node's prompt from scratch for a fresh-session retry.

    Each successive attempt simplifies further: add explicit structure, then
    truncate and show the exact JSON shape, then a minimal "do your best" form.
    The goal is to coax a usable answer out of a node the model couldn't (or
    wouldn't) answer as originally phrased.
    """
    output_keys = [o.key for o in node.outputs]
    strategies = [
        # 1: keep the full task, add explicit structure and an output contract.
        lambda p: (
            f"Please complete the following task carefully:\n\n{p}\n\n"
            f"IMPORTANT: reply with ONLY a JSON object containing these keys: "
            f"{output_keys}."
        ),
        # 2: trim the task and show the exact JSON skeleton to fill in.
        lambda p: (
            f"Task: {p[:1000]}\n\n"
            "Reply with ONLY this JSON object, filling in the values:\n"
            "```json\n{\n"
            + "\n".join(f'  "{key}": <value>,' for key in output_keys)
            + "\n}\n```"
        ),
        # 3: minimal emergency form — reasonable values are acceptable.
        lambda p: (
            "Complete this task as best you can; if unsure, provide reasonable "
            f"values.\n\nTask summary: {p[:500]}\n\n"
            f"You MUST reply with ONLY a JSON object with keys: {output_keys}."
        ),
    ]
    idx = min(attempt - 1, len(strategies) - 1)
    return strategies[idx](original_prompt)


def _default_outputs(node: AgentNode) -> dict[str, Any]:
    """Outputs emitted when a node exhausts all retries/reframes and the runner
    falls back to "default to next node".

    The runner is generic and has no idea what a node's outputs *mean*, so the
    safe fallback value is whatever the workflow author declared on each output
    spec (``OutputSpec.default``, defaulting to ``None``). The step's recorded
    output plus the ⏭ log line make the fallback explicit for later inspection.
    """
    return {spec.key: spec.default for spec in node.outputs}


def _stream_events(
    proc: subprocess.Popen, node_id: str, timeout: float
) -> tuple[str, str | None, str, bool, bool, float | None]:
    """Consume Claude's stream-json line by line, echoing a concise live view to
    stdout and returning ``(result_text, session_id, diagnostics, timed_out,
    rate_limited, rate_reset_at)``.

    ``diagnostics`` accumulates anything that signals *how* a run failed —
    non-event output lines (e.g. "Spending cap reached") and error-result
    subtypes — so the caller can classify transient failures.

    ``rate_limited`` is True if any ``rate_limit_event`` reported the limit as hit;
    ``rate_reset_at`` is the most recent window-reset epoch seen (used only when the
    failure is otherwise determined to be a cap, for precise wait timing).

    ``timed_out`` indicates whether we exceeded the timeout waiting for a result."""
    result_text = ""
    session_id = None
    diagnostics: list[str] = []
    timed_out = False
    rate_limited = False
    rate_reset_at: float | None = None
    start_time = time.time()
    
    assert proc.stdout is not None
    
    # Set non-blocking mode for stdout to enable timeout handling
    
    while True:
        # Check if we've exceeded the total timeout
        elapsed = time.time() - start_time
        if elapsed > timeout:
            timed_out = True
            break
        
        # Wait for data with a short timeout to check overall timeout periodically
        ready, _, _ = select.select([proc.stdout], [], [], min(1.0, timeout - elapsed))
        if not ready:
            # No data available, check if process is still running
            if proc.poll() is not None:
                # Process has ended
                break
            continue
        
        raw_line = proc.stdout.readline()
        if not raw_line:
            # EOF reached
            break
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON line (e.g. merged stderr) — surface it so logs aren't silent
            # and keep it as a diagnostic for failure classification.
            print(f"[{node_id}] {line}", flush=True)
            diagnostics.append(line)
            continue

        etype = event.get("type")
        if etype == "result":
            result_text = event.get("result", "") or result_text
            # An error result carries the reason in its subtype / is_error flag.
            if event.get("is_error") or event.get("subtype") not in (None, "success"):
                diagnostics.append(str(event.get("subtype") or "") + " " + str(event.get("result") or ""))
        elif etype == "rate_limit_event":
            blocked, reset_at = _rate_limit_info(event)
            if reset_at is not None:
                rate_reset_at = reset_at  # last-seen window reset (used only if capped)
            if blocked:
                rate_limited = True
        elif etype == "system" and "session_id" in event:
            session_id = event["session_id"]
        _emit_event(node_id, event)

    return result_text, session_id, "\n".join(diagnostics), timed_out, rate_limited, rate_reset_at


def _emit_event(node_id: str, event: dict) -> None:
    """Print a concise, human-readable view of a Claude stream-json event."""
    etype = event.get("type")
    if etype == "assistant":
        for block in event.get("message", {}).get("content", []) or []:
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    print(f"[{node_id}] {text}", flush=True)
            elif btype == "tool_use":
                name = block.get("name", "?")
                line = f"[{node_id}] ⚙ {name} {_tool_summary(block.get('input', {}))}".rstrip()
                print(line, flush=True)
    elif etype == "result":
        dur = event.get("duration_ms")
        print(f"[{node_id}] ✓ result received" + (f" ({dur} ms)" if dur else ""), flush=True)


def _tool_summary(inp: dict) -> str:
    for key in ("file_path", "path", "command", "pattern", "url", "query", "description"):
        value = inp.get(key)
        if value:
            flat = " ".join(str(value).split())
            return flat[:120] + "…" if len(flat) > 120 else flat
    return ""


def _extract_outputs(text: str, node: AgentNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    parsed = _parse_json_from_text(text)
    if parsed is None:
        raise OutputParseError(
            f"Node '{node.id}' declared outputs {[o.key for o in node.outputs]} "
            f"but Claude response contained no parseable JSON"
        )

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            raise OutputParseError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in agent JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result


def _parse_json_from_text(text: str) -> dict | None:
    # Try fenced code block first
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try first top-level JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
