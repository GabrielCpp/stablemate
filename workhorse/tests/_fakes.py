"""Test doubles for the ports the runner is handed.

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

from workhorse.runner.backends import AgentBackend


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
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._now += timedelta(seconds=seconds)
