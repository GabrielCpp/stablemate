"""What one non-Claude turn yielded, and the one place such a turn is classified.

Every adapter that is not Claude ends its turn here: the JSONL backends
(codex/copilot/opencode) after ``stream_jsonl``, aider after its plain-text
transcript. The struct and the classifier live together because they are two halves
of one contract — what the stream accumulates, and how the accumulation becomes a
result or a ``BackendInvocationError``.

Nothing here names a CLI. A field only one backend needs does not belong on the
struct they all share (see ``opencode._OpenCodeEvents``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from workhorse import otel
from workhorse.runner import agent as _agent
from workhorse.runner.usage import TurnUsage


@dataclass(slots=True)
class TurnState:
    """What one non-Claude turn yielded, as its output streamed past.

    Mutable by construction: ``stream_jsonl``'s per-line callback and the
    per-CLI ``on_event`` adapter write into it event by event, the process
    outcome lands once the stream closes, and ``finalize_turn`` reads the
    finished value. It replaces a bare ``dict`` that four backends
    ``setdefault``-ed into with no shared declaration, and the four-element tuple
    that used to carry it back out.

    Every field here is one every backend has. A key only one CLI needs does not
    belong on the struct they all share — see ``opencode._OpenCodeEvents``.
    """

    result_text: str = ""
    session_id: str | None = None
    usage: TurnUsage = field(default_factory=TurnUsage)
    #: Anything signalling *how* a turn failed — non-JSON output lines and
    #: structured error events — for ``classify_turn`` to read.
    diagnostics: list[str] = field(default_factory=list)
    timed_out: bool = False
    returncode: int = 0

    @property
    def diagnostics_text(self) -> str:
        """The diagnostics as the single string ``classify_turn`` scans."""
        return "\n".join(self.diagnostics)


def read_session_id(session_id_path: Path | None) -> str | None:
    """The persisted session id for this node, if any (for --resume)."""
    if session_id_path and session_id_path.exists():
        sid = session_id_path.read_text().strip()
        return sid or None
    return None


def finalize_turn(
    backend_name,
    node_id,
    state: TurnState,
    session_id_path,
    timeout,
    rate_reset_at=None,
) -> str:
    """Classify a finished turn through the one shared classifier, so the JSONL/text
    backends and the Claude path produce identical failure messages and transient /
    overflow / non-recoverable verdicts. See ``agent.classify_turn``.

    ``rate_reset_at`` is an optional unix epoch when a cap's window reopens (the
    opencode/Codex path fetches it out-of-band); on a cap the classifier attaches it
    so the runner sleeps until exactly then instead of the blind default wait."""
    # The one place every non-Claude turn ends, so it is where usage reaches the
    # open turn span — no backend needs its own otel call, and a new backend gets
    # cost/token attribution by populating `state.usage` and nothing else.
    if not state.usage.is_empty:
        otel.turn_result(state.usage)
    return _agent.classify_turn(
        backend_name,
        node_id,
        result_text=state.result_text,
        diagnostics=state.diagnostics_text,
        timed_out=state.timed_out,
        returncode=state.returncode,
        timeout=timeout,
        session_id=state.session_id,
        session_id_path=session_id_path,
        rate_reset_at=rate_reset_at,
    )
