"""The newline-delimited-JSON event loop shared by the CLIs that speak one."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, Required, TypedDict, Unpack

from workhorse.config_run import AgentResilience
from workhorse.runner import failure as _failure
from workhorse.runner import process as _process
from workhorse.runner.backends import (
    AgentBackend,
    TurnRequest,
    ensure_prompt_is_not_in_argv,
    prepare_argv_prompt,
    warn_unenforced_confinement,
)
from workhorse.runner.backends.delegates import warn_unsupported
from workhorse.runner.backends.turn import (
    OnEvent,
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)

_LOG_RECORD = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+\s+(?:ERROR|WARN|INFO|DEBUG|TRACE)\b")

__all__ = ["JsonlBackend", "JsonlStream", "OnEvent", "stream_jsonl"]


class JsonlOptions(TypedDict, total=False):
    resilience: Required[AgentResilience]
    cwd: str | None
    env_extra: dict[str, str] | None
    non_failure_markers: tuple[str, ...]


class JsonlStream(Protocol):
    """Run one CLI turn and stream its NDJSON stdout."""

    def __call__(
        self,
        cmd: list[str],
        node_id: str,
        timeout: float,
        stdin_data: str | None,
        on_event: OnEvent,
        **options: Unpack[JsonlOptions],
    ) -> TurnState: ...


def stream_jsonl(
    cmd: list[str],
    node_id: str,
    timeout: float,
    stdin_data: str | None,
    on_event: OnEvent,
    **options: Unpack[JsonlOptions],
) -> TurnState:
    """Run ``cmd``, feed ``stdin_data`` (or nothing), and stream its JSONL stdout, invoking ``on_event(event, state, node_id)`` per parsed object.

    A text line carrying one of ``non_failure_markers`` is printed but is no diagnostic, so a CLI's report of an ordinary event never reads as a failure.
    Neither are the lines that continue it, such as the file text a missed patch quotes, up to the next event or log record.
    """
    non_failure_markers = options.get("non_failure_markers", ())
    state = TurnState()
    early_abort = [""]
    excused = [False]

    def on_line(raw: str) -> bool:
        line = raw.strip()
        if not line:
            return False
        before = len(state.diagnostics)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = None
        if isinstance(event, dict):
            excused[0] = False
            on_event(event, state, node_id)
        else:
            print(f"[{node_id}] {line}", flush=True)
            if any(marker in line for marker in non_failure_markers):
                excused[0] = True
            elif not excused[0] or _LOG_RECORD.match(line):
                excused[0] = False
                state.diagnostics.append(line)
        new_diag = "\n".join(state.diagnostics[before:])
        if not early_abort[0] and new_diag and _failure.is_cap(new_diag):
            early_abort[0] = "cap"
            return True
        if not early_abort[0] and new_diag and _failure.is_transient(new_diag):
            early_abort[0] = "transient"
            return True
        return False

    timed_out, returncode = _process.stream_subprocess(
        cmd, node_id, timeout, on_line,
        resilience=options["resilience"],
        stdin_data=stdin_data, cwd=options.get("cwd"), env_extra=options.get("env_extra"),
    )
    state.timed_out = timed_out or bool(early_abort[0])
    state.returncode = returncode
    return state


class JsonlBackend(AgentBackend):
    """An ``AgentBackend`` whose CLI speaks NDJSON, holding the loop it speaks it with."""

    def __init__(self, stream: JsonlStream = stream_jsonl) -> None:
        self.stream = stream

    def execute_argv(
        self,
        turn: TurnRequest,
        command: Callable[[str, Path | None, str | None], list[str]],
        on_event: OnEvent,
    ) -> str:
        """Run a turn of a CLI that takes its prompt as an argument and runs without a confined box.

        ``command`` builds the argv from the bounded prompt message, the attachment staged for an oversized prompt and the session id to resume.
        """
        warn_unsupported(self.name, turn.delegates)
        warn_unenforced_confinement(self.name, turn.node_id, turn.agent)
        sid = read_session_id(turn.session_id_path)
        argv_prompt, attachment = prepare_argv_prompt(turn.prompt, turn.prompt_path)
        cmd = command(argv_prompt, attachment, sid)
        if sid:
            print(f"[{turn.node_id}] 🔄 Resuming {self.name} session: {sid[:8]}...", flush=True)
        ensure_prompt_is_not_in_argv(turn.prompt, cmd)
        state = self.stream(
            cmd, turn.node_id, turn.timeout, None, recording(on_event, turn.session_id_path),
            resilience=turn.resilience, cwd=turn.cwd,
            env_extra=self.harness_env(),
        )
        return finalize_turn(self.name, turn.node_id, state, turn.session_id_path, turn.timeout)
