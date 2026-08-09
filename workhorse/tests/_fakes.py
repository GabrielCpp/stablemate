"""Test doubles for the ports the runner is handed, plus the one shared assertion helper.

The ladder in ``runner/ladder.py`` drives the agent CLI through the ``AgentBackend``
port it is *given*, so a test states the CLI's behaviour by injecting a backend rather
than reaching into ``agent`` and replacing one specific CLI's private turn function
(rule 5: a monkeypatched private name is a missing injection point). One fake serves
every such test, so the seam is defined once.

Imported as ``from _fakes import FakeBackend`` — ``tests/`` is on ``sys.path`` both
when a file is run standalone (``uv run python tests/test_x.py``) and under pytest.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from workhorse import otel
from workhorse.runner.backends import AgentBackend


def present[T](value: T | None) -> T:
    """``value`` with its ``None`` ruled out — for a lookup the test arranged to hit.

    ``select_next`` answers `WorkItem | None` because a worklist can be empty; a test
    that just built a three-item list is not that caller, and saying so keeps the
    assertion about the item rather than about the lookup.
    """
    assert value is not None
    return value


class FakeBackend(AgentBackend):
    """An ``AgentBackend`` whose two operations are plain functions the test supplies.

    ``turn`` is called as ``turn(prompt, node_id, session_id_path, model, **kwargs)`` —
    the port's own shape. ``compact`` is called as
    ``compact(session_id_path, node_id, model, **kwargs)``. Either may be omitted when
    the test under way never reaches it. ``harness_env`` is overridden so the fake
    never reads the operator's config off disk.
    """

    name = "fake"
    supports_compaction = True

    def __init__(self, turn: Any = None, compact: Any = None) -> None:
        self._turn = turn
        self._compact = compact

    def harness_env(self) -> dict[str, str]:
        return {}

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        if self._turn is None:
            raise AssertionError("FakeBackend.run_turn called but no turn was supplied")
        return self._turn(prompt, node_id, session_id_path, model, **kwargs)

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> bool:
        if self._compact is None:
            raise AssertionError("FakeBackend.compact called but no compact was supplied")
        return self._compact(session_id_path, node_id, model, **kwargs)


class FakeClock:
    """A ``Clock`` that records what it was asked to wait and never waits.

    The same injection point, for time: a cap that reopens eight days out is a list of
    numbers rather than a patched ``time.sleep``. Sleeping advances ``now``, so a test
    can assert on the "resuming around" label the ladder computes from it.
    """

    def __init__(self, now: datetime | None = None) -> None:
        # A fixed, unremarkable instant so a test that prints the resume time reads the
        # same on every machine; tests that care state their own.
        self._now = now or datetime(2026, 1, 1, 12, 0, 0)
        self._elapsed = 0.0
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        """Elapsed seconds since this clock's own zero, moved only by ``sleep``.

        Deliberately not derived from the wall clock a test may have set to an
        arbitrary instant: what a caller measures with this is a duration, so it
        starts at zero and advances only when the test says time passed.
        """
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._elapsed += seconds
        self._now += timedelta(seconds=seconds)


class RecordingTelemetry(otel._NullTelemetry):
    """Telemetry that remembers what was published, for tests that assert on it.

    Subclassing the null adapter means every signal a test does *not* care about
    stays the same no-op it is in production, and only the two recorded here need
    a body. Install it with ``otel.install(otel.TelemetryHost(active=fake))`` and
    put the returned host back afterwards — the module-level functions delegate to
    whatever host is installed, so nothing has to be assigned over.
    """

    def __init__(self) -> None:
        #: (node, idle_s, elapsed_s) per liveness beat.
        self.beats: list[tuple[str, float, float]] = []
        #: One entry per ``set_labels`` call, in order.
        self.labels: list[dict[str, str]] = []
        #: Explicit state execution boundaries, distinct from durable checkpoints.
        self.states: list[tuple[str, str, int, str | None]] = []
        #: One entry per state span closed by an interruption: state, cut reason.
        self.cuts: list[tuple[str, str]] = []
        #: Completed wait boundaries: action, token, kind/outcome, node.
        self.waits: list[tuple[str, int, str, str]] = []
        #: One entry per ``turn_event``: name, error flag, attributes.
        self.events: list[tuple[str, bool, dict[str, Any]]] = []
        #: Agent-turn span boundaries: the node each turn opened on, and the error each
        #: one closed with (``None`` = closed cleanly). Unequal lengths mean a span was
        #: left dangling, which is the failure a test about an interrupted turn is for.
        self.turns_opened: list[str] = []
        self.turns_closed: list[str | None] = []
        #: Run finalizations: the status each ``end_run`` published, in order. The host
        #: makes the first one win, so a second entry means a test called it itself.
        self.ended: list[str] = []
        self._wait_token = 0

    def enabled(self) -> bool:
        return True

    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None:
        self.beats.append((node_id, idle_s, elapsed_s))

    def set_labels(self, labels: dict[str, str]) -> None:
        self.labels.append(dict(labels))

    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None:
        self.events.append((name, error, dict(attrs)))

    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
    ) -> None:
        self.turns_opened.append(node_id)

    def turn_end(
        self, error: str | None = None, error_class: str = "", error_kind: str = ""
    ) -> None:
        self.turns_closed.append(error)

    def state_start(self, state: str, seq: int) -> None:
        self.states.append(("start", state, seq, None))

    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None:
        self.states.append(("end", state, seq, next_state))
        if cut:
            self.cuts.append((state, cut))

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        self.ended.append(status)

    def wait_start(self, kind: str, node_id: str) -> int:
        self._wait_token += 1
        self.waits.append(("start", self._wait_token, kind, node_id))
        return self._wait_token

    def wait_end(self, token: int, outcome: str = "completed") -> None:
        self.waits.append(("end", token, outcome, ""))
