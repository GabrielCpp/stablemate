"""The identity of one agent-node *visit*, shared by everything that writes about it.

Three writers describe the same visit and none of them can see the others: the engine
renders a prompt and stores it (:mod:`workhorse.artifacts`), the runner records which
backend session answered it (:mod:`workhorse.runner.failure`), and the capture layer
lands the transcript. Until they agree on a name for the visit, the three files can only
be joined by guessing — and a node visited five times in a loop makes the guess wrong.

So the name is minted once, here, and read by all three:

``<generation>-<seq>-<node>``

- **generation** — how many times this run directory has been *started*, read from the
  ``resume_generation`` file :mod:`workhorse.otel` maintains. Read-only: incrementing it
  is that module's job, and doing it twice would make a restart look like two.
- **seq** — a monotone per-run visit counter, kept in a file beside it so it survives a
  restart. Durable rather than in-process precisely because generation is *not* always
  incremented (telemetry off does not bump it), and two visits sharing a name is the one
  failure this module exists to prevent.
- **node** — the node id, so a human reading ``ls`` gets the answer without a join.

Zero-padded so a lexical sort is a chronological one, which is what makes ``ls`` and a
glob agree with the order the visits actually happened in.

Nothing here may fail a run: a counter that cannot be read or written falls back to the
process-local one, which is worse at surviving a restart and just as good at being
unique within it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

#: Where the per-run visit counter lives — beside ``sessions.jsonl`` and
#: ``resume_generation``, because durable state about a run belongs with the run.
SEQ_FILE = "turn_seq"

#: :mod:`workhorse.otel` owns this file; this module only ever reads it.
GENERATION_FILE = "resume_generation"


@dataclass(frozen=True, slots=True)
class VisitKey:
    """One agent-node visit, named the same way by every writer that describes it."""

    generation: int
    seq: int
    node: str
    #: The session chain this visit ran on, or "" for the usual clean context. It is
    #: deliberately not part of `slug`: the visit is still one visit, and putting a
    #: chain key in the filename would rename every artifact of a node on the day its
    #: loop joins a chain, breaking every path a reader had written down.
    chain: str = ""

    @property
    def slug(self) -> str:
        """The directory / filename stem. Padding is for sort order, not for looks."""
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
    """The next visit number, advancing the durable counter when there is one.

    The in-process fallback is kept in step with the durable value, so a counter that
    becomes unreadable mid-run continues from where it was rather than restarting at 1
    and colliding with the visits already on disk.
    """
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
    """Mint the key for a visit to ``node_id`` and make it the current one.

    ``run_dir`` is the run's own directory — the one holding ``sessions.jsonl`` — so a
    nested flow's visits are numbered in the same sequence as its parent's rather than
    restarting inside the sub-scope.

    ``chain`` is the session chain the visit runs on (:mod:`workhorse.sessions`), or ""
    for the usual clean context. It rides on the key because the three writers that
    describe a visit are exactly the three places a reader would have to join to find
    out whether two laps shared a conversation.
    """
    global _current
    with _lock:
        key = VisitKey(read_generation(run_dir), _next_seq(run_dir), node_id, chain)
        _current = key
        return key


def current() -> VisitKey | None:
    """The visit in flight, or None outside one.

    None rather than a zeroed key: a writer that would otherwise stamp
    ``000-00000-`` on something no visit produced is better off writing nothing.
    """
    return _current


def clear() -> None:
    """Forget the current visit. Tests use this; a run has no need to."""
    global _current, _fallback_seq
    with _lock:
        _current = None
        _fallback_seq = 0
