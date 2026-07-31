"""The newline-delimited-JSON event loop shared by the CLIs that speak one.

Codex, Copilot and OpenCode all stream NDJSON on stdout. The loop below is generic;
each backend supplies an ``on_event`` callback that pulls the final answer text and
the resumable session id out of its own event vocabulary into the shared
``TurnState``.

It is also those backends' one dependency on a live subprocess, so it is declared as
a port (``JsonlStream``) and held as a field (``JsonlBackend.stream``) rather than
reached for as a module global. A test that wants to see the argv an adapter built,
or hand it a canned turn, constructs the adapter with its own stream.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from workhorse.config_run import AgentResilience
from workhorse.runner import failure as _failure
from workhorse.runner import process as _process
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.turn import TurnState


class OnEvent(Protocol):
    """One parsed NDJSON object, folded into the turn's accumulating state.

    ``event`` stays a plain mapping on purpose: it is another tool's output, read
    tolerantly for the handful of keys this adapter knows and shrugged at otherwise.
    What gets *owned* is the far side — ``TurnState``.
    """

    def __call__(self, event: dict[str, Any], state: TurnState, node_id: str) -> None: ...


class JsonlStream(Protocol):
    """Run one CLI turn and stream its NDJSON stdout. ``stream_jsonl`` is the
    implementation; a test is the other one."""

    def __call__(
        self,
        cmd: list[str],
        node_id: str,
        timeout: float,
        stdin_data: str | None,
        on_event: OnEvent,
        *,
        resilience: AgentResilience,
        cwd: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> TurnState: ...


def stream_jsonl(
    cmd: list[str],
    node_id: str,
    timeout: float,
    stdin_data: str | None,
    on_event: OnEvent,
    *,
    resilience: AgentResilience,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> TurnState:
    """Run ``cmd``, feed ``stdin_data`` (or nothing), and stream its JSONL stdout,
    invoking ``on_event(event, state, node_id)`` per parsed object.

    Streams through ``process.stream_subprocess`` so the timeout, hard watchdog, and
    process-group kill behave identically to every other harness. ``cwd`` sets the
    subprocess working directory (previously silently dropped here, so Codex/Copilot/
    OpenCode nodes always ran in the launching process's CWD regardless of a node's
    ``cwd:``). ``env_extra`` layers the harness's operator-configured environment
    (``[harness.<backend>].env``) over the inherited one.
    Returns the finished ``TurnState``. Non-JSON lines are echoed and kept as
    diagnostics so failure classification can see them."""
    state = TurnState()
    early_abort = [""]

    def on_line(raw: str) -> bool:
        line = raw.strip()
        if not line:
            return False
        before = len(state.diagnostics)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"[{node_id}] {line}", flush=True)
            state.diagnostics.append(line)
        else:
            on_event(event, state, node_id)
        # As soon as a recoverable provider failure appears — whether as a raw log
        # line or a structured error event — abort the CLI's internal retry loop and
        # hand recovery to Workhorse's bounded backoff policy. Caps retain their
        # separate scheduled-reset path. Scan only newly-added diagnostics so this
        # stays O(n) over the stream.
        new_diag = "\n".join(state.diagnostics[before:])
        if not early_abort[0] and new_diag and _failure.is_cap(new_diag):
            early_abort[0] = "cap"
            return True  # signal stream_subprocess to break and kill the process
        if not early_abort[0] and new_diag and _failure.is_transient(new_diag):
            early_abort[0] = "transient"
            return True  # signal stream_subprocess to break and kill the process
        return False

    timed_out, returncode = _process.stream_subprocess(
        cmd, node_id, timeout, on_line,
        resilience=resilience,
        stdin_data=stdin_data, cwd=cwd, env_extra=env_extra,
    )
    state.timed_out = timed_out or bool(early_abort[0])
    state.returncode = returncode
    return state


class JsonlBackend(AgentBackend):
    """An ``AgentBackend`` whose CLI speaks NDJSON, holding the loop it speaks it with.

    The one field is the point. Codex, Copilot and OpenCode differ in argv and in
    event vocabulary, and share the streaming; three adapters each writing
    ``self.stream = stream`` is the repetition this exists to remove. It stays
    abstract — ``run_turn`` and ``compact`` are still each adapter's own.

    Assigned in ``__init__`` rather than declared as a class attribute so it lands on
    the instance: a plain function stored on a class becomes a bound method, and
    ``self.stream(cmd, ...)`` would quietly pass the backend as ``cmd``.
    """

    def __init__(self, stream: JsonlStream = stream_jsonl) -> None:
        self.stream = stream
