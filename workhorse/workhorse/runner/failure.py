"""How a finished agent-CLI turn is classified: the markers, the typed errors, and the one classifier every backend funnels through."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from workhorse import gitstate, otel, sessions, turnkey
from workhorse.runner import transcript

_CAP_MARKERS = (
    "spending cap", "usage limit", "weekly limit", "session limit", "quota",
    "key limit", "daily limit",
)
_LIMIT_STATUS_MARKERS = (
    "block", "reject", "exceed", "throttl", "reached", "denied", "over_limit", "limit_reached",
)

_TRANSIENT_MARKERS = (
    "spending cap",
    "usage limit",
    "weekly limit",
    "session limit",
    "quota",
    "key limit",
    "daily limit",
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
    "unable to connect",
    "econnrefused",
    "enotfound",
    "enetunreach",
    "eai_again",
    "socket hang up",
    "mid-response",
    "response above may be incomplete",
    "failed to execute statement",
    "failed query:",
)

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
    "dimension limit",
    "many-image requests",
)


_UNRESUMABLE_SESSION_MARKERS = (
    "no conversation found",
    "session not found",
    "no session found",
    "invalid session id",
    "could not resume",
    "failed to resume",
)


class OutputParseError(RuntimeError):
    """The agent's response could not be parsed into the node's declared outputs."""


class BackendInvocationError(RuntimeError):
    """An agent-CLI turn failed (non-zero exit, or no result event)."""

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
        self.timed_out = timed_out
        self.reset_at = reset_at


def error_kind(exc: BaseException) -> str:
    """Which recovery layer a failure belongs to, as one low-cardinality word."""
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
    """A scheduled-reset cap (spending/usage/weekly/session/quota), distinct from a short transient like a rate limit or overload that clears in seconds."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CAP_MARKERS)


def is_context_overflow(diagnostics: str) -> bool:
    """The model's context window was exhausted mid-node (the headless CLI returned instead of compacting)."""
    low = diagnostics.lower()
    return any(marker in low for marker in _CONTEXT_OVERFLOW_MARKERS)


def is_unresumable_session(diagnostics: str) -> bool:
    """The CLI refused the session id it was asked to resume."""
    low = diagnostics.lower()
    return any(marker in low for marker in _UNRESUMABLE_SESSION_MARKERS)


def rate_limit_info(event: dict) -> tuple[bool, float | None]:
    """Read a ``rate_limit_event`` → ``(blocked, reset_at_epoch)``."""
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
    """Map ``node_id`` to the harness CLI ``session_id`` so the agent's session transcript can be recovered after the run — ``opencode export <session_id>`` (and the equivalent for other backends) yields its full reasoning/tool trace, which the node's ``prompt.md`` / ``output.json`` do not carry."""
    if not (session_id_path and session_id):
        return
    otel.turn_session(session_id)
    row: dict[str, Any] = {"node": node_id, "session_id": session_id}
    key = turnkey.current()
    if key is not None and key.node == node_id:
        row["generation"] = key.generation
        row["seq"] = key.seq
    row["ts"] = int(time.time())
    if backend:
        row["backend"] = backend
    head = gitstate.current_head()
    if head:
        row["head"] = head
    try:
        manifest = sessions.run_dir_of(session_id_path) / "sessions.jsonl"
        with manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass
    transcript.capture(backend, node_id, session_id)


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
    generated_tokens: int | None = None,
) -> str:
    """Classify a finished agent-CLI turn uniformly for EVERY backend."""
    tail = f": {diagnostics.strip()}" if diagnostics.strip() else ""
    capped = rate_limited or is_cap(diagnostics)
    cap_reset_at = rate_reset_at if capped else None

    if capped:
        raise BackendInvocationError(
            f"{backend_name} usage/spending cap reached for node '{node_id}'{tail}",
            transient=True,
            reset_at=cap_reset_at,
        )

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
            session_id_path.parent.mkdir(parents=True, exist_ok=True)
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
        if generated_tokens:
            if session_id_path and session_id:
                session_id_path.parent.mkdir(parents=True, exist_ok=True)
                session_id_path.write_text(session_id)
                record_session_map(session_id_path, node_id, session_id, backend_name)
            raise BackendInvocationError(
                f"{backend_name} spent {generated_tokens} generation tokens without "
                f"answering for node '{node_id}' — output budget exhausted while "
                f"reasoning{tail}",
                transient=False,
                overflow=True,
            )
        raise BackendInvocationError(
            f"No result text from {backend_name} for node '{node_id}'{tail}",
            transient=True,
            reset_at=cap_reset_at,
        )
    if session_id_path and session_id:
        session_id_path.parent.mkdir(parents=True, exist_ok=True)
        session_id_path.write_text(session_id)
        record_session_map(session_id_path, node_id, session_id, backend_name)
    return result_text
