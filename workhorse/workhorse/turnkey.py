"""The identity of one agent-node *visit*, shared by everything that writes about it."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

SEQ_FILE = "turn_seq"

GENERATION_FILE = "resume_generation"


@dataclass(frozen=True, slots=True)
class VisitKey:
    """One agent-node visit, named the same way by every writer that describes it."""

    generation: int
    seq: int
    node: str
    chain: str = ""

    @property
    def slug(self) -> str:
        """The directory / filename stem."""
        return f"{self.generation:03d}-{self.seq:05d}-{self.node}"

    def attributes(self) -> dict[str, int | str]:
        """The same identity as record fields, for a JSONL line or a span."""
        fields: dict[str, int | str] = {
            "generation": self.generation,
            "seq": self.seq,
            "node": self.node,
        }
        if self.chain:
            fields["chain"] = self.chain
        return fields


_lock = threading.Lock()
_current: VisitKey | None = None
_fallback_seq = 0


def read_generation(run_dir: Path | None) -> int:
    """This run directory's start counter, or 0 when there is none to read."""
    if run_dir is None:
        return 0
    try:
        return int((run_dir / GENERATION_FILE).read_text().strip())
    except (OSError, ValueError):
        return 0


def _next_seq(run_dir: Path | None) -> int:
    """The next visit number, advancing the durable counter when there is one."""
    global _fallback_seq
    _fallback_seq += 1
    if run_dir is None:
        return _fallback_seq
    path = run_dir / SEQ_FILE
    try:
        previous = int(path.read_text().strip())
    except (OSError, ValueError):
        previous = 0
    seq = max(previous, _fallback_seq - 1) + 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(seq))
    except OSError:
        pass
    _fallback_seq = seq
    return seq


def begin(run_dir: Path | None, node_id: str, *, chain: str = "") -> VisitKey:
    """Mint the key for a visit to ``node_id`` and make it the current one."""
    global _current
    with _lock:
        key = VisitKey(read_generation(run_dir), _next_seq(run_dir), node_id, chain)
        _current = key
        return key


def current() -> VisitKey | None:
    """The visit in flight, or None outside one."""
    return _current


def clear() -> None:
    """Forget the current visit."""
    global _current, _fallback_seq
    with _lock:
        _current = None
        _fallback_seq = 0
