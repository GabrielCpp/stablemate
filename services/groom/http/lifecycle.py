"""The lifecycle matrices: one for a run, one for the attendant switch. Each scene
names its condition and the calls that reach it; each action aims one call at the
run there, or builds none where the pair cannot occur."""

from __future__ import annotations

from datetime import date
from typing import Callable, cast

from ostler.book import Axes, Impossible, Scene

from ..fixtures import Look, Push, Query, Settings, asking, blocked, finished, looking_at, running, stranger
from ..model.records import Run
from ..model.state import GroomApp
from . import endpoints as e
from .endpoints import PushBlocked, PushExited, PushProgress, ReadAttend, ReadFleet, ReadWorker, SetAttend

TODAY = date(2026, 11, 4)


def run_of(model: GroomApp) -> Run | None:
    """The run the scene is about: the first one kept."""
    return next(iter(model.runs), None)


def _look(build: Callable[[Look], object]) -> Callable[[GroomApp], object]:
    """Aim a read at the run the scene is about, or at a run nobody pushed where the scene has none."""

    def aim(model: GroomApp) -> object:
        run = run_of(model)
        return build(looking_at(run.container_id if run else None))

    return aim


def _on_run(build: Callable[[Push], object], none: Callable[[], object] | None = None) -> Callable[[GroomApp], object]:
    def aim(model: GroomApp) -> object:
        run = run_of(model)
        if run is not None:
            return build(Push.of(run))
        return none() if none else Impossible("no run is on the fleet to aim at")

    return aim


RUN_SCENES = (
    Scene("(none)", "the fleet holds no run of ours", lambda today: ()),
    Scene("running", "the run reported progress and holds no gate", lambda today: (PushProgress(running(current_node="build")),)),
    Scene("blocked", "the run waits on one gate", lambda today: (PushBlocked(blocked()),)),
    Scene("finished", "the run exited with a code", lambda today: (PushExited(finished(2)),)),
)

RUN_ACTIONS: dict[str, Callable[[GroomApp], object]] = {
    "report progress": _on_run(lambda p: PushProgress(p), lambda: PushProgress(running())),
    "report progress in a node": _on_run(lambda p: PushProgress(p.but(current_node="test")), lambda: PushProgress(running(current_node="test"))),
    "report a gate": _on_run(lambda p: PushBlocked(p.but(file_path="gates/approve.md", question="Ship it?")), lambda: PushBlocked(blocked())),
    "report a second gate": _on_run(lambda p: PushBlocked(p.but(file_path="gates/review.md", question="Review done?")), lambda: PushBlocked(blocked(path="gates/review.md"))),
    "report an exit": _on_run(lambda p: PushExited(p.but(exit_code=1)), lambda: PushExited(finished(1))),
    "report a clean exit": _on_run(lambda p: PushExited(p.but(exit_code=0)), lambda: PushExited(finished(0))),
    "read the fleet": _on_run(lambda p: ReadFleet(query=Query(q=p.name)), lambda: ReadFleet(query=Query())),
    "read the run": _on_run(lambda p: ReadWorker(p), lambda: ReadWorker(stranger())),
    "read its gate": _look(lambda k: e.ReadOutbox(k)),
    "answer its gate": _look(lambda k: e.AnswerGate(k.but(file_path="gates/approve.md", answer="yes"))),
    "read its inbox": _look(lambda k: e.ReadInbox(k)),
    "leave it a message": _look(lambda k: e.LeaveMessage(k.but(body="hold on"))),
    "leave it an empty message": _look(lambda k: e.LeaveMessage(k.but(body=""))),
    "read its overview": _look(lambda k: e.ReadOverview(k)),
    "read its activity": _look(lambda k: e.ReadActivity(k)),
    "read its activity with logs": _look(lambda k: e.ReadActivity(k.but(logs=1))),
    "read its records": _look(lambda k: e.ReadRecords(k)),
    "read its records from a cursor": _look(lambda k: e.ReadRecords(k.but(before="12.5|3|7", limit=5, metrics=1))),
    "read its records from a bad cursor": _look(lambda k: e.ReadRecords(k.but(before="later"))),
    "search it": _look(lambda k: e.SearchRun(k.but(q="deploy"))),
    "read an entry": _look(lambda k: e.ReadEntry(k.but(key="step:plan"))),
    "read a turn": _look(lambda k: e.ReadTurn(k.but(slug="plan-1"))),
    "read its archive overview": _look(lambda k: e.ReadArchiveOverview(k)),
    "read its archive activity": _look(lambda k: e.ReadArchiveActivity(k)),
    "read its archive records": _look(lambda k: e.ReadArchiveRecords(k)),
    "search its archive": _look(lambda k: e.SearchArchive(k.but(q="deploy"))),
    "read an archive entry": _look(lambda k: e.ReadArchiveEntry(k.but(key="step:plan"))),
    "read an archive turn": _look(lambda k: e.ReadArchiveTurn(k.but(slug="plan-1"))),
    "list its files": _look(lambda k: e.ReadFiles(k.but(repo="shop"))),
    "read a file": _look(lambda k: e.ReadFile(k.but(repo="shop", path="src/app.py"))),
    "read its change": _look(lambda k: e.ReadDiff(k.but(repo="shop"))),
    "read its change since the branch": _look(lambda k: e.ReadDiff(k.but(view="branch"))),
    "retry its summary": _look(lambda k: e.RetryHistory(k)),
}


def run_state(model: GroomApp) -> str:
    run = run_of(model)
    return run.lifecycle if run else "(none)"


ATTEND_SCENES = (
    Scene("Off", "no attendant answers the gates", lambda today: ()),
    Scene("Headless", "an attendant answers the gates", lambda today: (SetAttend(Settings(enabled=True)),)),
)

ATTEND_ACTIONS: dict[str, Callable[[GroomApp], object]] = {
    "turn on": lambda m: SetAttend(Settings(enabled=True)),
    "turn off": lambda m: SetAttend(Settings(enabled=False)),
    "read the switch": lambda m: ReadAttend(),
    "read the fleet": lambda m: ReadFleet(query=Query()),
    "read the queue": lambda m: e.ReadAttendQueue(),
    "read the log": lambda m: e.ReadAttendSessions(),
}

SERVICE_SCENES = (Scene("serving", "groom answers and holds nothing the book did not push", lambda today: ()),)

SERVICE_ACTIONS: dict[str, Callable[[GroomApp], object]] = {
    "list the checkouts": lambda m: e.ReadRepos(),
    "read the live runs": lambda m: e.ReadLive(query=asking()),
    "read one live run": lambda m: e.ReadLive(query=asking(run=stranger().container_id)),
    "read the history": lambda m: e.ReadHistory(query=asking()),
    "read the history with archives": lambda m: e.ReadHistory(query=asking(archives=1)),
    "scan again": lambda m: e.Refresh(),
    "reload every sidecar": lambda m: e.Reload(query=asking()),
    "reload one sidecar": lambda m: e.Reload(query=asking(container_id=stranger().container_id)),
    "read an attendance": lambda m: e.ReadAttendSession(looking_at()),
    "stop an attendant": lambda m: e.StopAttendant(looking_at()),
    "read the queues": lambda m: e.ReadQueues(),
    "enqueue on an unknown queue": lambda m: e.Enqueue(looking_at().but(queue="nightly")),
    "read an unknown queue": lambda m: e.ReadQueueItems(looking_at().but(queue="nightly")),
    "cancel an item": lambda m: e.CancelItem(looking_at().but(queue="nightly", item_id="i1")),
    "stop an item": lambda m: e.StopItem(looking_at().but(queue="nightly", item_id="i1")),
}

MATRICES = (
    Axes[GroomApp]("run", TODAY, RUN_SCENES, RUN_ACTIONS, run_state,
                   state_of=lambda m, r: "blocked" if cast(Run, r).gates else cast(Run, r).state, entities=lambda m: m.runs),
    Axes[GroomApp]("service", TODAY, SERVICE_SCENES, SERVICE_ACTIONS, lambda m: "serving",
                   state_of=lambda m, _: "serving"),
    Axes[GroomApp]("attendant", TODAY, ATTEND_SCENES, ATTEND_ACTIONS, lambda m: type(m).__name__,
                   state_of=lambda m, _: type(m).__name__),
)
