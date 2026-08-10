"""How a finished agent-CLI turn is classified: the markers, the typed errors, and
the one classifier every backend funnels through."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from workhorse import gitstate, otel, turnkey

# A subscription "cap" is a transient failure that recovers on a SCHEDULE — the
# spending/usage/session window resets at a wall-clock time (e.g. "resets 3:50am",
# "session limit · resets 11:30am"), not after a few seconds. We wait it out until
# the reset rather than burning the short-backoff budget (and never reframe
# the prompt — re-asking a capped subscription can't help). This is baked into the
# core agent so a single run survives a cap with no supervisor — and because an AI
# "fixer" can't help here anyway: it would run on the same capped subscription.
# "key limit"/"daily limit" cover a *provider API key* that has hit its per-key
# daily ceiling (e.g. OpenRouter: "Key limit exceeded (daily limit)"). Like a
# subscription cap this clears on a wall-clock schedule (the daily reset), not after
# a few seconds — so it is waited out, never reframed. Critically, reframing or
# defaulting through it would silently advance the run past a gate on empty outputs
# (which is exactly how a daily-limit hit on a grounding node dumped a run onto the
# operator gate); the cap path pauses and re-runs the SAME node instead.
_CAP_MARKERS = (
    "spending cap", "usage limit", "weekly limit", "session limit", "quota",
    "key limit", "daily limit",
)
# The cap ladder's own knobs — the fallback wait when the reset time can't be parsed,
# the margin added after a parsed reset so we wake just AFTER the window reopens, the
# "still paused" tick, the bound on consecutive waits, and the upper bound on a single
# structured (resetsAt-derived) sleep — are fields on ``AgentResilience``
# (``cap_default_wait_s`` / ``cap_wait_margin_s`` / ``cap_tick_s`` / ``max_cap_waits`` /
# ``cap_max_wait_s``), injected into the functions in ``runner.caps``.
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
    "key limit",      # provider API key hit its ceiling (cap; see _CAP_MARKERS)
    "daily limit",    # …specifically the per-day reset, e.g. OpenRouter daily key cap
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
    # The turn never reached the API at all — DNS, routing or the socket failed
    # before a request went out. Observed as "API Error: Unable to connect to API
    # (ENOTIMP)", which matched no marker above and so killed an unattended run
    # over a blip that the next turn would not have seen. Nothing was consumed and
    # nothing is wrong with the prompt, which is what makes it retryable.
    "unable to connect",
    "econnrefused",
    "enotfound",
    "enetunreach",
    "eai_again",
    "socket hang up",
    # A stream that began then was cut off upstream ("API Error: Server error
    # mid-response. The response above may be incomplete.") — a partial 5xx after
    # the result started, exit 1. Retryable: a fresh turn usually completes. Kept
    # narrow on purpose so a *deterministic* "Unexpected server error, check logs"
    # (see test_finalize_turn_non_recoverable_names_each_backend) stays non-recoverable.
    "mid-response",
    "response above may be incomplete",
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
    # Claude rejects sessions with too many large images — treat as overflow so the
    # runner compacts (purging the images from context) and restarts the node rather
    # than dying as non-recoverable.
    "dimension limit",
    "many-image requests",
)


class OutputParseError(RuntimeError):
    """The agent's response could not be parsed into the node's declared outputs.

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
    ``ladder.AgentRunner``), so it is NOT retried with backoff (that would just
    overflow again) and is handled before the generic reframe ladder.
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


def error_kind(exc: BaseException) -> str:
    """Which recovery layer a failure belongs to, as one low-cardinality word.

    The ladder already draws these distinctions to decide what to do next, but until
    this existed none of them survived into telemetry: `turn_end` carried `str(exc)`
    and nothing else, so a store could count failed turns and never say whether they
    were rate limits riding out an outage, context overflows, or a CLI that was
    genuinely broken. Those need opposite responses, and telling them apart by
    grepping message text is exactly the fragility `is_transient` exists to contain.

    The precedence matches `AgentRunner.turn`'s own, and has to. `overflow` is checked
    first because compaction is a layer above the retry loop, and `cap` before
    `timeout` because a cap-triggered early abort also carries `timed_out` (the stream
    loop reaps the process when the window closes) — reading that as a timeout would
    file an eight-day scheduled wait under "the node ran too long".
    """
    if isinstance(exc, OutputParseError):
        return "parse"
    if isinstance(exc, BackendInvocationError):
        if exc.overflow:
            return "overflow"
        if exc.reset_at is not None or is_cap(str(exc)):
            return "cap"
        if exc.timed_out:
            return "timeout"
        if exc.transient:
            return "transient"
    return "fatal"


def is_transient(diagnostics: str) -> bool:
    low = diagnostics.lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


def is_cap(diagnostics: str) -> bool:
    """A scheduled-reset cap (spending/usage/weekly/session/quota), distinct from a
    short transient like a rate limit or overload that clears in seconds."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CAP_MARKERS)


def is_context_overflow(diagnostics: str) -> bool:
    """The model's context window was exhausted mid-node (the headless CLI returned
    instead of compacting). Recovered by compacting the session, not by retrying."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CONTEXT_OVERFLOW_MARKERS)


def rate_limit_info(event: dict) -> tuple[bool, float | None]:
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


def record_session_map(
    session_id_path: Path | None,
    node_id: str,
    session_id: str | None,
    backend: str = "",
) -> None:
    """Map ``node_id`` to the harness CLI ``session_id`` so the agent's session
    transcript can be recovered after the run — ``opencode export <session_id>``
    (and the equivalent for other backends) yields its full reasoning/tool trace,
    which the node's ``prompt.md`` / ``output.json`` do not carry.

    Two sinks, because they answer the mapping at different times:

    - the open agent-turn span gets a ``session.id`` attribute (queryable in groom
      / any trace store, live and after the fact);
    - an append-only ``sessions.jsonl`` beside ``.session_id`` keeps the history on
      disk. ``.session_id`` is overwritten every node, so it only ever holds the
      *current* node's session; the manifest is what survives to map a *past* node
      back to its session, and it needs no collector.

    A node can appear more than once (loop revisits, compact/reframe within a
    node), so the mapping is node -> sessions; consumers dedup on read. Best-effort
    like the rest of telemetry: a write failure must never fault an unattended run.

    ``node`` alone does not address a *particular* visit, which is what a reader
    debugging a node that thrashed actually needs. So each line also carries:

    - ``generation`` / ``seq`` — the visit key (:mod:`workhorse.turnkey`), the same one
      naming that visit's stored prompt and transcript. ``(generation, ts)`` is a total
      order that survives a checkpoint rewind, because a rewind cannot decrease the
      generation and the manifest is append-only: re-running a node adds rows, it never
      rewrites one.
    - ``ts`` — epoch seconds, so a line can be placed against the run's spans and logs
      without inferring order from file position.
    - ``backend`` — which CLI's vocabulary the session id is in; ``opencode export`` and
      ``~/.claude/projects`` are not interchangeable and the id does not say which.
    - ``head`` — the commit the tree was on when the turn was recorded, observed, not
      assumed (:mod:`workhorse.gitstate`).

    Every added key is optional on read: lines written before this still parse, and a
    consumer must treat an absent key as "not recorded", never as a default.
    """
    if not (session_id_path and session_id):
        return
    otel.turn_session(session_id)
    row: dict[str, Any] = {"node": node_id, "session_id": session_id}
    key = turnkey.current()
    if key is not None and key.node == node_id:
        # Guarded on the node: a turn taken outside the visit the engine opened (a
        # library caller driving the runner directly) is better unnumbered than
        # numbered wrong.
        row["generation"] = key.generation
        row["seq"] = key.seq
    row["ts"] = int(time.time())
    if backend:
        row["backend"] = backend
    head = gitstate.current_head()
    if head:
        row["head"] = head
    try:
        manifest = session_id_path.parent / "sessions.jsonl"
        with manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def classify_turn(
    backend_name: str,
    node_id: str,
    *,
    result_text: str | None,
    diagnostics: str,
    timed_out: bool,
    returncode: int,
    timeout: float,
    session_id: str | None = None,
    session_id_path: Path | None = None,
    rate_limited: bool = False,
    rate_reset_at: float | None = None,
) -> str:
    """Classify a finished agent-CLI turn uniformly for EVERY backend.

    The single source of truth for turning a finished subprocess into either a
    result string or a typed ``BackendInvocationError`` — shared by the Claude
    path (``backends.claude``) and the JSONL/text path (``backends.turn``)
    so the failure messages and the transient/overflow/cap/non-recoverable
    classification are identical no matter which CLI ran.

    Ladder (first match wins):
    - cap marker / rate-limit signal → a scheduled-reset cap (carries ``reset_at``),
      checked BEFORE ``timed_out`` because a cap often makes the CLI hang until the
      watchdog reaps it — framing that as a cap (not a timeout) is what lets the run
      wait the window out instead of reporting a bogus "Timeout waiting for result".
    - ``timed_out`` → transient (the watchdog already reaped the process group).
    - context-overflow marker → ``overflow`` (recovered by compaction, not retry);
      the session id is persisted so the runner can compact-and-continue it.
    - non-zero exit → transient *iff* the output matches a retryable marker (or a
      rate limit fired); otherwise NON-RECOVERABLE (``transient=False``) so the
      runner stops instead of reframing a crashed CLI.
    - empty result → transient (the CLI was likely interrupted).
    A cap-like failure carries ``reset_at`` so the runner can sleep until the
    window reopens; a plain transient must not, or it would look like a cap.
    The session id is persisted on success and on overflow.
    """
    tail = f": {diagnostics.strip()}" if diagnostics.strip() else ""
    capped = rate_limited or is_cap(diagnostics)
    cap_reset_at = rate_reset_at if capped else None

    # A spending/usage cap can surface as the CLI *hanging*: it logs the limit error
    # to its stream (e.g. opencode: "AI_APICallError: The usage limit has been
    # reached") but never exits, so the watchdog reaps it and reports timed_out=True.
    # Classify the cap FIRST — before the timed_out branch — so the run waits the
    # window out (until reset_at when the CLI gave one) under a truthful "cap reached"
    # message, instead of mis-framing it as a plain "Timeout waiting for result …
    # after Ns" that buries the real cause and reads like a stuck node.
    if capped:
        raise BackendInvocationError(
            f"{backend_name} usage/spending cap reached for node '{node_id}'{tail}",
            transient=True,
            reset_at=cap_reset_at,
        )

    # JSONL backends ask stream_subprocess to stop as soon as an error event/log
    # identifies a short transient. That intentional early abort uses the same
    # ``timed_out`` transport signal as the wall-clock watchdog, so preserve the
    # provider error as the cause and do not tell the retry it exhausted its node
    # budget. This is what turns e.g. OpenCode's ProviderHeaderTimeoutError into
    # Workhorse's bounded backoff instead of waiting for the CLI's internal loop.
    if timed_out and is_transient(diagnostics):
        raise BackendInvocationError(
            f"Transient {backend_name} provider failure for node '{node_id}'{tail}",
            transient=True,
        )

    if timed_out:
        raise BackendInvocationError(
            f"Timeout waiting for result from {backend_name} for node '{node_id}'"
            f" after {int(timeout)}s{tail}",
            transient=True,
            timed_out=True,
        )
    if is_context_overflow(diagnostics):
        if session_id_path and session_id:
            session_id_path.write_text(session_id)
            record_session_map(session_id_path, node_id, session_id, backend_name)
        raise BackendInvocationError(
            f"Context window exhausted for node '{node_id}'{tail}",
            transient=False,
            overflow=True,
        )
    if returncode != 0:
        raise BackendInvocationError(
            f"{backend_name} CLI exited with code {returncode} for node '{node_id}'{tail}",
            transient=is_transient(diagnostics) or rate_limited,
            reset_at=cap_reset_at,
        )
    if not result_text:
        raise BackendInvocationError(
            f"No result text from {backend_name} for node '{node_id}'{tail}",
            transient=True,
            reset_at=cap_reset_at,
        )
    if session_id_path and session_id:
        session_id_path.write_text(session_id)
        record_session_map(session_id_path, node_id, session_id, backend_name)
    return result_text
