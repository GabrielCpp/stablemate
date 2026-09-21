"""Test doubles for the ports a workflow drive is handed."""

from __future__ import annotations

from typing import Any

from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner


class StubRunner(AgentRunner):
    """An ``AgentRunner`` whose one operation is a plain function the test supplies."""

    def __init__(self, agent: Any) -> None:
        super().__init__(backend=NullBackend())
        self._agent = agent

    def run(self, *args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return self._agent(*args, **kwargs)
