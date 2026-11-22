"""What groom does. A push upserts the run it names and answers that it took it or
ignored it; a read shows the fleet, one run or the attendant switch."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ostler.book import Action, Actor, Become, Create, Show, Transaction, Update

from ..fixtures import Look, Push, Query, Reply, Settings
from . import rules
from .records import BLOCKED, GATE_STATUS, FINISHED, PREVIEW_MAX, RUNNING, Ack, AttendSettings, Filter, Gate, GateView, Head, Metrics, Run, Running, Strip, Worker
from . import views
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
        activity_rev=0,
        metrics_rev=0,
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


class ReadOutbox(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        run = s.runs[a.run_id] if a.run_id in s.runs else None
        if run is None or not run.gates:
            return Show(views.Outbox(False))
        gate = run.gates[0]
        return Show(views.Outbox(True, gate.file_path, gate.question, GATE_STATUS))


def _refuse_unknown_run(a: Look, s: GroomApp, reason: str) -> Show:
    if a.run_id not in s.runs:
        return Show(views.Notice(False, "no such run"))
    return Show(views.Notice(False, reason))


class AnswerGate(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return _refuse_unknown_run(a, s, "unknown workspace volume for this container")


class ReadInbox(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Inbox())


class LeaveMessage(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        if a.run_id in s.runs and not a.body:
            return Show(views.Notice(False, "message body is required"))
        return _refuse_unknown_run(a, s, "no run directory yet")


class ReadOverview(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Overview(a.run_id or ""))


class ReadActivity(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Activity(a.run_id or ""))


class ReadRecords(Action[Look, GroomApp]):
    accept = Look
    rules = (rules.bad_cursor,)

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Records(a.run_id or "", metrics=bool(a.metrics)))


class SearchRun(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Matches(a.run_id or "", a.q or ""))


class ReadEntry(Action[Look, GroomApp]):
    accept = Look
    rules = (rules.no_entry,)

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Transaction:
        return Transaction()


class ReadTurn(Action[Look, GroomApp]):
    accept = Look
    rules = (rules.no_turn,)

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Transaction:
        return Transaction()


class ReadArchive(Action[Look, GroomApp]):
    accept = Look
    rules = (rules.no_archive,)

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Transaction:
        return Transaction()


class ReadFiles(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Tree())


class ReadFile(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        path = a.path or ""
        return Show(views.FileText(path, views.language_of(path)))


class ReadDiff(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Change())


class ReadRepos(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show()


class ReadLive(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show()


class ReadHistory(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.History())


class RetryHistory(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Done())


class Refresh(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Refreshed())


class Reload(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Reloaded())


class ReadAttendQueue(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.AttendQueue(s.attend))


class ReadAttendSessions(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.AttendSessions(s.attend))


class ReadAttendSession(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        ident = a.session_id or ""
        return Show(views.AttendSession(ident, f"claude --resume {ident}"))


class StopAttendant(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Done())


class ReadQueues(Action[object, GroomApp]):
    @staticmethod
    def reduce(a: object, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Queues())


class Enqueue(Action[Look, GroomApp]):
    accept = Look
    rules = (rules.no_queue,)

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Transaction:
        return Transaction()


class ReadQueueItems(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.QueueItems())


class DropItem(Action[Look, GroomApp]):
    accept = Look

    @staticmethod
    def reduce(a: Look, s: GroomApp, by: Actor | None) -> Show:
        return Show(views.Done())


class OpenRun(Action[Push, Dashboard]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction()


class AnswerFromPage(Action[Reply, Dashboard]):
    accept = Reply
    rules = (rules.workspace_unreachable,)

    @staticmethod
    def reduce(a: Reply, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction()
