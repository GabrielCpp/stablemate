"""The newline-delimited-JSON event loop shared by the CLIs that speak one.

Codex, Copilot and OpenCode all stream NDJSON on stdout. The loop below is generic;
each backend supplies an ``on_event`` callback that pulls the final answer text and
the resumable session id out of its own event vocabulary into the shared
``TurnState``.
"""

from __future__ import annotations

import json

from workhorse.runner import failure as _failure
from workhorse.runner import process as _process
from workhorse.runner.backends.turn import TurnState


def stream_jsonl(
    cmd, node_id, timeout, stdin_data, on_event, *, resilience, cwd=None, env_extra=None
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
