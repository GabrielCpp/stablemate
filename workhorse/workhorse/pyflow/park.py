"""Blocking a run on an Await's file until it is answered, over the file and the control socket, and writing the ask."""
from __future__ import annotations

import logging
from pathlib import Path

from workhorse import control, gates, reload
from workhorse.control import NULL_CHANNEL, ControlChannel, Request, wait_until
from workhorse.pyflow.engine import RunEnv
from workhorse.pyflow.errors import WorkflowFailed
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger("workhorse.engine")

HEARTBEAT_S = 300.0


def answered(path: Path) -> bool:
    """Whether the operator gate at `path` has actually been answered."""
    try:
        text = path.read_text()
    except OSError:
        return False
    return gates.status_of(text) != "AWAITING_OPERATOR"


def wait_for_answer(
    path: Path,
    *,
    interval: float,
    clock: Clock = SYSTEM_CLOCK,
    channel: ControlChannel = NULL_CHANNEL,
    log: logging.Logger | None = None,
    deadline: float | None = None,
    kind: str = "operator",
) -> Request | None:
    """Block until the gate at `path` is answered, or a control request arrives."""
    log = log or logger
    waited = 0.0
    operator = kind == "operator"
    if operator:
        since = clock.now().isoformat()
        control.questions_with(lambda: _pending_gate(path, kind, since))
    try:
        while True:
            if answered(path):
                log.info("[workhorse] await  → %s answered; resuming", path)
                return None
            if deadline is not None and clock.now().timestamp() > deadline:
                raise WorkflowFailed(
                    f"run exceeded its wall-clock budget while waiting on {path}",
                    failure_class="await-deadline-exceeded",
                    artifacts={"gate": str(path)},
                )
            request = wait_until(
                lambda: answered(path),
                timeout=interval,
                clock=clock,
                channel=channel,
                tick=interval,
            )
            if request is not None:
                if request.action != control.ANSWER:
                    return request
                if operator:
                    _consume_answer(request, path, channel, log)
                else:
                    channel.reply(
                        {
                            "ok": False,
                            "error": "this run is not blocked on an operator gate "
                            "right now",
                        }
                    )
                continue
            waited += interval
            if waited % HEARTBEAT_S < interval:
                condition = (
                    "STATUS: ANSWERED in" if operator else "the job to finish in"
                )
                log.info(
                    "[workhorse] await  → still waiting for %s %s (%ds)",
                    condition,
                    path,
                    int(waited),
                )
    finally:
        if operator:
            control.questions_with(None)


def _pending_gate(path: Path, kind: str, since: str) -> list[dict[str, object]]:
    """What this run is blocked on, for the channel's `questions` verb."""
    if answered(path):
        return []
    return [{"path": str(path), "question": wait_question(path), "kind": kind, "since": since}]


def _gate_question(path: Path) -> str:
    """Read the durable question, including any earlier exchanges on this gate."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def wait_question(path: Path) -> str:
    """The open question on `path`, bounded, for the readers this run tells.

    A gate accumulates every exchange it has ever held, so its whole text is the wrong
    payload for a wait span or a `questions` reply. Both carry the gate's path, so a
    reader that wants the history reads it from disk.
    """
    return gates.latest_question(_gate_question(path))


def _consume_answer(
    request: Request, path: Path, channel: ControlChannel, log: logging.Logger
) -> None:
    """One `answer` request, judged and — when it is this gate's — written to disk."""
    asked = str(path)
    if request.path and request.path != asked:
        channel.reply(
            {"ok": False, "error": f"this run is waiting on {asked}, not {request.path}"}
        )
        return
    if answered(path):
        channel.reply({"ok": False, "error": "already answered"})
        return
    try:
        text = path.read_text()
    except OSError:
        text = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gates.apply_answer(text, request.body))
    except OSError as exc:
        channel.reply({"ok": False, "error": f"could not write the gate file: {exc}"})
        return
    channel.reply({"ok": True, "path": asked})
    log.info("[workhorse] await  → %s answered over the control socket", path)


def park_on(path: Path, env: RunEnv, *, kind: str) -> None:
    """Block on `path` until answered, honouring control requests while parked."""
    while True:
        interrupted = wait_for_answer(
            path,
            interval=env.config.await_poll_s,
            clock=env.clock,
            channel=control.armed(),
            log=env.log,
            deadline=env.deadline,
            kind=kind,
        )
        if interrupted is None:
            return
        cut = reload.cut_by(interrupted)
        if cut is not None:
            env.log.info("[workhorse] reload → requested while parked on %s", path)
            raise reload.ReloadRequested(
                f"reload requested while parked on {path}",
                core=cut.core,
                cli=cut.cli,
            )


def ask(path: Path, questions: str, log: logging.Logger) -> None:
    """Write the ask, so the operator has something to answer."""
    if not questions:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.read_text()
    except OSError:
        existing = ""
    if existing.strip():
        path.write_text(gates.append_operator_gate(existing, questions))
    else:
        path.write_text(gates.format_operator_gate(questions))
