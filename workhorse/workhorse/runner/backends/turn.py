"""What one non-Claude turn yielded, and the one place such a turn is classified."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from workhorse import otel
from workhorse.runner import failure as _failure
from workhorse.runner.usage import TurnUsage


@dataclass(slots=True)
class TurnState:
    """What one non-Claude turn yielded, as its output streamed past."""

    result_text: str = ""
    session_id: str | None = None
    usage: TurnUsage = field(default_factory=TurnUsage)
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
    """Classify a finished turn through the one shared classifier, so the JSONL/text backends and the Claude path produce identical failure messages and transient / overflow / non-recoverable verdicts."""
    if not state.usage.is_empty:
        otel.turn_result(state.usage)
    return _failure.classify_turn(
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
        generated_tokens=state.usage.generated_tokens,
    )
