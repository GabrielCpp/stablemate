"""Test doubles for the ports a workflow drive is handed.

Imported as ``from _fakes import StubRunner`` — ``tests/`` is on ``sys.path`` under
pytest, the same convention ``workhorse/tests/_fakes.py`` uses.
"""

from __future__ import annotations

from typing import Any

from workhorse.runner.backends.null import NullBackend
from workhorse.runner.ladder import AgentRunner


class StubRunner(AgentRunner):
    """An ``AgentRunner`` whose one operation is a plain function the test supplies.

    The engine drives every agent turn through ``RunEnv.agent_runner``, so a suite that
    wants to script the model injects one here rather than replacing a name inside the
    ladder module. That matters beyond tidiness: the ladder is what binds a backend, the
    resilience knobs and the clock together, and a run whose turns are scripted has no
    backend to bind — ``AgentRunner.from_config`` would resolve a real agent CLI on the
    first turn.

    A real ``AgentRunner`` and not merely one shaped like it: ``RunEnv.agent_runner`` is
    typed as the service, and what a scripted suite replaces is the turn, not the type
    the engine is handed. The backend is the null adapter — the ladder this overrides is
    never entered, and if it ever were, "no CLI selected" is the honest answer.

    ``run`` forwards verbatim to the supplied callable, whose shape is the port's own:
    ``(node, context, workflow_dir, session_id_path, *, resume_session=False,
    run_dir=None) -> (rendered_prompt, raw_reply)``. Everything above it — prompt
    resolution, the reply schema, the recorded turn — stays the real code path.
    """

    def __init__(self, agent: Any) -> None:
        super().__init__(backend=NullBackend())
        self._agent = agent

    def run(self, *args: Any, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        return self._agent(*args, **kwargs)
