"""The lifecycle matrices of the page: one for a run as the list shows it, one for the
attendant switch in the settings pane."""

from __future__ import annotations

from datetime import date
from typing import Callable, cast

from ostler.book import Axes, Impossible, Scene

from ..fixtures import Push, Query, Settings, blocked, finished, judging, replying, running
from ..model.records import Run
from ..model.state import Dashboard
from .interactions import (
    AnswerTheGate, FilterTheList, ReadActivity, ReadTheMedian, ReadTheOpenedRun, OpenAttendant, OpenDispatch, OpenHistory, OpenRun, OpenRuns, OpenSettings, ReportExit,
    ReportGate, ReportProgress, SwitchTheAttendant,
)

TODAY = date(2026, 11, 4)


def run_of(model: Dashboard) -> Run | None:
    return next(iter(model.runs), None)


def _on_run(build: Callable[[Push], object], none: Callable[[], object] | None = None) -> Callable[[Dashboard], object]:
    def aim(model: Dashboard) -> object:
        run = run_of(model)
        if run is not None:
            return build(Push.of(run))
        return none() if none else Impossible("no run is on the list to aim at")

    return aim


RUN_SCENES = (
    Scene("(none)", "the list holds no run of ours", lambda today: ()),
    Scene("running", "the run reported progress and holds no gate", lambda today: (ReportProgress(running(current_node="build")),)),
    Scene("blocked", "the run waits on one gate", lambda today: (ReportGate(blocked()),)),
    Scene("finished", "the run exited with a code", lambda today: (ReportExit(finished(2)),)),
)

RUN_ACTIONS: dict[str, Callable[[Dashboard], object]] = {
    "report progress": _on_run(lambda p: ReportProgress(p), lambda: ReportProgress(running())),
    "report progress in a node": _on_run(lambda p: ReportProgress(p.but(current_node="test")), lambda: ReportProgress(running(current_node="test"))),
    "report a gate": _on_run(lambda p: ReportGate(p.but(file_path="gates/approve.md", question="Ship it?")), lambda: ReportGate(blocked())),
    "report a second gate": _on_run(lambda p: ReportGate(p.but(file_path="gates/review.md", question="Review done?")), lambda: ReportGate(blocked(path="gates/review.md"))),
    "report an exit": _on_run(lambda p: ReportExit(p.but(exit_code=1)), lambda: ReportExit(finished(1))),
    "report a clean exit": _on_run(lambda p: ReportExit(p.but(exit_code=0)), lambda: ReportExit(finished(0))),
    "filter by its name": _on_run(lambda p: FilterTheList(Query(q=p.name)), lambda: FilterTheList(Query())),
    "clear the filter": lambda m: FilterTheList(Query()),
    "open it": _on_run(lambda p: OpenRun(p), lambda: Impossible("no run is on the list to open")),
    "read its activity": _on_run(lambda p: ReadActivity(p), lambda: Impossible("no run is on the list to read")),
    "answer its gate": lambda m: _answer(m),
}


def _answer(model: Dashboard) -> object:
    run = run_of(model)
    if run is None or not run.gates:
        return Impossible("no run on the list waits on a gate")
    return AnswerTheGate(replying(run.container_id, "yes"))


def run_state(model: Dashboard) -> str:
    run = run_of(model)
    return run.lifecycle if run else "(none)"


ATTEND_SCENES = (
    Scene("Off", "no attendant answers the gates", lambda today: ()),
    Scene("Headless", "an attendant answers the gates", lambda today: (SwitchTheAttendant(Settings(enabled=True)),)),
)

ATTEND_ACTIONS: dict[str, Callable[[Dashboard], object]] = {
    "turn on": lambda m: SwitchTheAttendant(Settings(enabled=True)),
    "turn off": lambda m: SwitchTheAttendant(Settings(enabled=False)),
    "open settings": lambda m: OpenSettings(),
    "return to the runs": lambda m: OpenRuns(),
    "open history": lambda m: OpenHistory(),
    "open the attendant": lambda m: OpenAttendant(),
    "open dispatch": lambda m: OpenDispatch(),
}

HISTORY_SCENES = (Scene("(none)", "History holds the ended runs of a workflow no earlier cell made", lambda today: ()),)

HISTORY_ACTIONS: dict[str, Callable[[Dashboard], object]] = {
    "judge a run that cost more": lambda m: ReadTheMedian(judging()),
    "judge a run with dearer peers": lambda m: ReadTheMedian(judging(peers=(20.0, 22.0, 24.0, 26.0, 28.0))),
    "judge a run that cost less": lambda m: ReadTheMedian(judging(each=0.5)),
    "judge a run with four other runs": lambda m: ReadTheMedian(judging(peers=(1.0, 2.0, 3.0, 4.0))),
    "judge a run that failed": lambda m: ReadTheMedian(judging(ending="failed")),
    "judge a run whose cost is an estimate": lambda m: ReadTheMedian(judging(estimate=True)),
    "judge a run with no finished item": lambda m: ReadTheMedian(judging(items=0)),
    "judge a failed run with no other run": lambda m: ReadTheMedian(judging(ending="failed", peers=())),
    "open a run that gave up": lambda m: ReadTheOpenedRun(judging(ending="gave-up")),
    "open a run with no ending": lambda m: ReadTheOpenedRun(judging(ending="none")),
    "open an estimate with no ending": lambda m: ReadTheOpenedRun(judging(estimate=True, ending="none")),
    "open an estimate that failed": lambda m: ReadTheOpenedRun(judging(estimate=True, ending="failed")),
    "open a run with no other run": lambda m: ReadTheOpenedRun(judging(peers=())),
    "open a run with one other run": lambda m: ReadTheOpenedRun(judging(peers=(1.0,))),
    "open a run that cost more": lambda m: ReadTheOpenedRun(judging()),
    "open a run that cost less": lambda m: ReadTheOpenedRun(judging(each=0.5)),
    "open a run with four other runs": lambda m: ReadTheOpenedRun(judging(peers=(1.0, 2.0, 3.0, 4.0))),
    "open a run that failed": lambda m: ReadTheOpenedRun(judging(ending="failed")),
    "open a run whose cost is an estimate": lambda m: ReadTheOpenedRun(judging(estimate=True)),
    "open a run with no finished item": lambda m: ReadTheOpenedRun(judging(items=0)),
}

MATRICES = (
    Axes[Dashboard]("run", TODAY, RUN_SCENES, RUN_ACTIONS, run_state,
                    state_of=lambda m, r: "blocked" if cast(Run, r).gates else cast(Run, r).state, entities=lambda m: m.runs),
    Axes[Dashboard]("history", TODAY, HISTORY_SCENES, HISTORY_ACTIONS, lambda m: "(none)", state_of=lambda m, _: "(none)"),
    Axes[Dashboard]("attendant", TODAY, ATTEND_SCENES, ATTEND_ACTIONS, lambda m: type(m).__name__,
                    state_of=lambda m, _: type(m).__name__),
)
