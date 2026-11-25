from __future__ import annotations

import asyncio
from pathlib import Path

from groom import (
    live,
    projection,
    sidecar_hub,
    state,
)
from groom.gates import answer_gate, native_questions
from groom.models import (
    AnswerResult,
    WorkflowContainer,
    WorkflowState,
)
from groom.native import _watch_transcript
from workhorse import control


def _same_gate(run_path: str, file_path: str) -> bool:
    """Whether the path a run reports for its gate names the same file as the (possibly workspace-relative) path a groom row carries."""
    rel = file_path.lstrip("/")
    return bool(run_path) and (run_path == file_path or run_path.endswith(f"/{rel}"))


async def _answer_via_socket(
    wf: WorkflowContainer | None, file_path: str, answer: str
) -> AnswerResult | None:
    """Deliver one answer over the run's control socket, or ``None`` when the file fallback should decide instead."""
    if wf is None:
        return None
    listing = await _run_questions(wf)
    if not listing or not listing.get("ok"):
        return None
    questions = [q for q in listing.get("questions") or [] if isinstance(q, dict)]
    match = next(
        (q for q in questions if _same_gate(str(q.get("path", "")), file_path)), None
    )
    if match is None:
        return None
    request = control.Request(
        action=control.ANSWER, path=str(match.get("path", "")), body=answer
    )
    if wf.native:
        try:
            reply = await asyncio.to_thread(control.send, wf.runs_volume, request)
        except (FileNotFoundError, control.ControlProtocolError, control.Unanswered):
            return None
    else:
        try:
            reply = await sidecar_hub.answer_gate(
                wf.container_id, "", request.path, answer
            )
        except sidecar_hub.SidecarError:
            return None
        if reply.get("error") == "no listener":
            return None
    if not reply:
        return None
    if reply.get("ok"):
        return AnswerResult(ok=True, message="answered over the run's control socket")
    error = str(reply.get("error", ""))
    if error == "already answered":
        return AnswerResult(ok=False, message=error)
    return None


async def _run_questions(wf: WorkflowContainer) -> dict | None:
    """The one-shot `questions` round-trip — used only by the answer flow."""
    if wf.native:
        if not wf.runs_volume:
            return None
        return await native_questions(wf.runs_volume, "gate one-shot", wf.container_id) or None
    try:
        reply = await sidecar_hub.ask_questions(wf.container_id)
    except sidecar_hub.SidecarError:
        return None
    if reply.get("error") == "no listener":
        return None
    return reply or None


async def _answer(wf: WorkflowContainer | None, container_id: str, file_path: str, answer: str) -> AnswerResult:
    """Write an operator's answer into one gate and settle the fleet around it — the state flip, the log, the broadcast."""
    gate = wf.gates.get(file_path) if wf else None
    tel = projection.telemetry_for(wf) if wf else None
    if (gate and gate.kind == "machine") or (
        tel and tel.wait_kind == "machine" and _same_gate(tel.wait_gate_path, file_path)
    ):
        return AnswerResult(ok=False, message="machine waits require their producer's result")
    workspace_volume = (gate.base if gate and gate.base else wf.workspace_volume) if wf else ""
    allow_headerless = bool(gate and gate.legacy_headerless)
    if allow_headerless:
        run = projection.telemetry_for(wf) if wf else None
        allow_headerless = bool(run and run.wait_kind == "operator"
                                and _same_gate(run.wait_gate_path, file_path))
    socket_result = await _answer_via_socket(wf, file_path, answer)
    if socket_result is not None:
        result = socket_result
        if result.ok:
            state.clear_gate(container_id, file_path)
    else:
        answer_path = file_path
        if wf and wf.native and gate and Path(file_path).is_absolute():
            workspace_volume = str(Path(file_path).parent)
            answer_path = Path(file_path).name
        result = await answer_gate(
            container_id,
            answer_path,
            answer,
            workspace_volume=workspace_volume,
            native=bool(wf and wf.native),
            allow_headerless=allow_headerless,
        )
    if result.ok:
        state.clear_gate(container_id, file_path)
    state.record_log(
        {
            "event": "answer",
            "container_id": container_id,
            "file_path": file_path,
            "ok": result.ok,
            "message": result.message,
            "via": "socket" if socket_result is not None else "file",
        }
    )
    if result.ok and wf is not None and not wf.gates and wf.state == WorkflowState.BLOCKED:
        wf.state = WorkflowState.RUNNING

    live.mark_fleet()
    live.mark_run(container_id)
    if result.ok:
        await state.broadcast(
            {"type": "answered", "id": container_id, "file_path": file_path}
        )
    return result


def _workflow_by_run_id(run_id: str) -> WorkflowContainer | None:
    """A run addressed by run id rather than container id."""
    wf = state.WORKFLOWS.get(run_id)
    if wf is not None:
        return wf
    for candidate in state.WORKFLOWS.values():
        if candidate.run_id == run_id:
            return candidate
    return None


async def _handle_command(data: dict, queue: asyncio.Queue | None = None) -> None:
    cmd = data.get("cmd")
    if cmd == "watch":
        if queue is None:
            return
        run_id = str(data.get("run_id", ""))
        state.watch(queue, run_id)
        if run_id:
            wf = state.WORKFLOWS.get(run_id)
            if wf is not None:
                _watch_transcript(wf)
                await live.open_detail(queue, run_id)
        return
    if cmd != "answer":
        return
    container_id = str(data.get("workflow_id", ""))
    file_path = str(data.get("file_path", ""))
    answer = str(data.get("answer", ""))
    wf = state.WORKFLOWS.get(container_id)
    result = await _answer(wf, container_id, file_path, answer)
    if not result.ok and queue is not None:
        await state.send(queue, projection.answer_rejected_message(container_id, file_path, result.message))
