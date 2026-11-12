"""What groom does. A push upserts the run it names and answers that it took it or
ignored it; a read shows the fleet, one run or the attendant switch."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ostler.book import Action, Actor, Become, Create, Show, Transaction, Update

from ..fixtures import Push, Query, Settings
from .records import BLOCKED, FINISHED, PREVIEW_MAX, RUNNING, Ack, AttendSettings, Filter, Gate, GateView, Head, Metrics, Run, Running, Strip, Worker
from .state import FILTER_KEY, Dashboard, DashboardHeadless, DashboardOff, GroomApp, Headless, Off


def handle(container_id: str | None) -> str:
    return (container_id or "")[:12]


def _text(value: str | None) -> str:
    return value or ""


def _upsert(a: Push, s: GroomApp, **changes: object) -> Transaction:
    cid = handle(a.container_id)
    if cid in s.runs:
        current = s.runs[cid]
        name = a.name if a.name is not None else current.name
        repo_name = a.repo_name if a.repo_name is not None else current.repo_name
        repo_branch = a.repo_branch if a.repo_branch is not None else current.repo_branch
        fields = {"name": name, "repo_name": repo_name, "repo_branch": repo_branch, **changes}
        return Transaction(Update(s.runs, cid, _replace(current, fields)), says=(Ack(True),))
    fields = {"name": a.name or cid, "repo_name": _text(a.repo_name), "repo_branch": _text(a.repo_branch), **changes}
    return Transaction(Create(s.runs, _replace(Run(cid, cid), fields)), says=(Ack(True),))


def _replace(run: Run, fields: dict[str, Any]) -> Run:
    return replace(run, **fields)


class PushProgress(Action[Push, GroomApp]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: GroomApp, by: Actor | None) -> Transaction | Show:
        if not handle(a.container_id):
            return Show(Ack(False))
        changes: dict[str, object] = {"state": RUNNING}
        cid = handle(a.container_id)
        if a.current_node is not None:
            changes["current_node"] = a.current_node
        elif cid not in s.runs:
            changes["current_node"] = ""
        return _upsert(a, s, **changes)


class PushBlocked(Action[Push, GroomApp]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: GroomApp, by: Actor | None) -> Transaction | Show:
        cid = handle(a.container_id)
        if not cid or not a.file_path:
            return Show(Ack(False))
        gate = Gate(a.file_path, _text(a.question))
        held = s.runs[cid].gates if cid in s.runs else ()
        gates = tuple(sorted((*(g for g in held if g.file_path != gate.file_path), gate), key=lambda g: g.file_path))
        return _upsert(a, s, state=BLOCKED, gates=gates)


class PushExited(Action[Push, GroomApp]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: GroomApp, by: Actor | None) -> Transaction | Show:
        cid = handle(a.container_id)
        if not cid:
            return Show(Ack(False))
        changes: dict[str, object] = {"state": FINISHED, "gates": ()}
        if a.exit_code is not None:
            changes["exit_code"] = a.exit_code
        return _upsert(a, s, **changes)


class ReadFleet(Action[Query, GroomApp]):
    accept = Query

    @staticmethod
    def reduce(a: Query, s: GroomApp, by: Actor | None) -> Show:
        return Show(s.fleet(a.q or ""))


def question_of(text: str) -> str:
    return text.strip()


def preview_of(question: str) -> str:
    for raw in question.splitlines():
        line = raw.strip().lstrip("#>*-` ").strip()
        if line:
            return line[:PREVIEW_MAX]
    return ""


def gate_view(gate: Gate) -> GateView:
    question = question_of(gate.question)
    return GateView(gate.file_path, question, preview_of(question))


def worker_of(run: Run) -> Worker:
    live = run.state != FINISHED and bool(run.current_node)
    return Worker(
        found=True,
        id=run.container_id,
        run_id=run.container_id,
        state=run.state,
        node=run.current_node,
        gates=tuple(gate_view(g) for g in run.gates),
        running=Running(run.current_node) if live else None,
        strip=Strip(run.current_node) if live else None,
        head=Head(
            id=run.container_id,
            handle=handle(run.container_id),
            state=run.state,
            repo=run.repo,
            live=run.live,
            live_label=run.live_label,
            node=run.current_node,
            exit_hint=run.exit_hint,
            exit_ok=run.exit_code == 0,
        ),
        metrics=Metrics(),
        logs=(),
        history=(),
        figures_rev=0,
    )


class ReadWorker(Action[Push, GroomApp]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: GroomApp, by: Actor | None) -> Show:
        cid = a.container_id or ""
        if cid in s.runs:
            return Show(worker_of(s.runs[cid]))
        return Show(Worker(found=False, id=cid))


class ReadAttend(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show(AttendSettings(s.attend))


class SetAttend(Action[Settings, GroomApp]):
    accept = Settings

    @staticmethod
    def reduce(a: Settings, s: GroomApp, by: Actor | None) -> Transaction:
        mode = Headless if a.enabled else Off
        return Transaction(Become(mode), says=(AttendSettings(mode.attend),))


class FilterRuns(Action[Query, Dashboard]):
    accept = Query

    @staticmethod
    def reduce(a: Query, s: Dashboard, by: Actor | None) -> Transaction:
        entity = Filter(FILTER_KEY, a.q or "")
        if FILTER_KEY in s.filters:
            return Transaction(Update(s.filters, FILTER_KEY, entity))
        return Transaction(Create(s.filters, entity))


class SwitchAttendant(Action[Settings, Dashboard]):
    accept = Settings

    @staticmethod
    def reduce(a: Settings, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(Become(DashboardHeadless if a.enabled else DashboardOff))


class Navigate(Action[object, Dashboard]):
    @staticmethod
    def reduce(a: object, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction()
