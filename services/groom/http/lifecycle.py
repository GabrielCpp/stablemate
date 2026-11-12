"""The lifecycle matrices: one for a run, one for the attendant switch. Each scene
names its condition and the calls that reach it; each action aims one call at the
run there, or builds none where the pair cannot occur."""

from __future__ import annotations

from datetime import date
from typing import Callable, cast

from ostler.book import Axes, Impossible, Scene

from ..fixtures import Push, Query, Settings, blocked, finished, running, stranger
from ..model.records import Run
from ..model.state import GroomApp
from .endpoints import PushBlocked, PushExited, PushProgress, ReadAttend, ReadFleet, ReadWorker, SetAttend

TODAY = date(2026, 11, 4)


def run_of(model: GroomApp) -> Run | None:
    """The run the scene is about: the first one kept."""
    return next(iter(model.runs), None)


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
}

MATRICES = (
    Axes[GroomApp]("run", TODAY, RUN_SCENES, RUN_ACTIONS, run_state,
                   state_of=lambda m, r: "blocked" if cast(Run, r).gates else cast(Run, r).state, entities=lambda m: m.runs),
    Axes[GroomApp]("attendant", TODAY, ATTEND_SCENES, ATTEND_ACTIONS, lambda m: type(m).__name__,
                   state_of=lambda m, _: type(m).__name__),
)
