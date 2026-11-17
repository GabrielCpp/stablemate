"""The tasks of the acme benchmark, and what a round of each does: the lines it prints, the notes its steps
leave in the sandbox, and the ledger and score it writes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from .files import SEEN

if TYPE_CHECKING:
    from .state import Root

Writes = tuple[tuple[str, tuple[str, ...]], ...]

PARK = "seen/interrupt-park.txt"


@dataclass(frozen=True)
class Effect:
    """What one step does: the notes it writes, the error it raises, whether it stops the round."""

    writes: Writes = ()
    error: str = ""
    interrupts: bool = False


@dataclass(frozen=True)
class Step:
    name: str
    effect: Callable[[Root, bool], Effect]


@dataclass(frozen=True)
class Scoring:
    headline: str
    detail: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True)
class Task:
    name: str
    steps: tuple[Step, ...]
    score: Scoring | None = None


def note(path: str, *lines: str) -> Writes:
    unknown = [line for line in lines if line not in SEEN[path]]
    assert not unknown, unknown
    return ((path, lines),)


def _plain_stage(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/plain-stage.txt", "stage holds README.md", "stage has no remote"))


def _plain_look(s: Root, pinned: bool) -> Effect:
    lines = ["pinned=True" if pinned else "pinned=False", "default_cli=claude", "artifacts_dir inside the stage"]
    if pinned:
        lines += ["pin fenced", "pin has no remote"]
    return Effect(note("seen/plain-project.txt", *lines))


def _override(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/override.txt", "default_cli=codex", "artifacts_dir kept"))


def _read_inputs(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/inputs.txt", "budget=1200.0", "only=A-1,B-2", "label=x,y", "strict=True", "absent=7.5", "none=0"))


def _misread(s: Root, pinned: bool) -> Effect:
    return Effect(error="TypeError: input 'strict' is bool, expected a number")


def _first(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/failing.txt", "first ran"))


def _boom(s: Root, pinned: bool) -> Effect:
    return Effect(error="RuntimeError: boom")


def _later(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/failing-later.txt", "later ran"))


def _exit_code(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/tools.txt", "exit=1", "ok=False"))


def _missing_tool(s: Root, pinned: bool) -> Effect:
    return Effect(error="RunError: no-such-program-xyz: not on PATH")


def _measure(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/scored.txt", "measured"))


def _start(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/interrupt-start.txt", "started"))


def _park(s: Root, pinned: bool) -> Effect:
    if PARK in s.files:
        return Effect(note(PARK, "parked", "passed"))
    return Effect(note(PARK, "parked"), interrupts=True)


def _finish(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/interrupt-finish.txt", "finished"))


def _helpers(s: Root, pinned: bool) -> Effect:
    return Effect(note("seen/library.txt", *SEEN["seen/library.txt"]))


TASKS = (
    Task("plain", (Step("copy", _plain_stage), Step("look", _plain_look))),
    Task("override", (Step("merged", _override),)),
    Task("inputs", (Step("read", _read_inputs), Step("misread", _misread))),
    Task("failing", (Step("first", _first), Step("boom", _boom), Step("later", _later))),
    Task("tools", (Step("exit_code", _exit_code), Step("missing_tool", _missing_tool))),
    Task("scored", (Step("measure", _measure),),
         Scoring("caught 7/9  missed 2", ("a: caught", "b: missed"), ("one trial was short",))),
    Task("interrupt", (Step("start", _start), Step("park", _park), Step("finish", _finish))),
    Task("library", (Step("helpers", _helpers),)),
)
NAMES = tuple(t.name for t in TASKS)


def listing() -> tuple[str, ...]:
    """The lines `paddock list` prints for the acme benchmark."""
    return tuple(f"acme  {t.name}  {len(t.steps)} steps  {'scored' if t.score else 'unscored'}" for t in TASKS)


def task_named(name: str | None) -> Task | None:
    return next((t for t in TASKS if t.name == name), None)


@dataclass(frozen=True)
class Round:
    """One numbered round of a task: its workspace, and its result once it has finished."""

    key: str
    task: str
    n: int
    open: bool
    finished: tuple[str, ...]
    pinned: bool
    segments: tuple[str, ...]
    ledger: tuple[str, ...] = ()
    score: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = ("paddock/paddock/names.py", "paddock/paddock/runner.py::_unfinished_workspace")

    def __str__(self) -> str:
        return f"{self.key} {'open' if self.open else 'done'}"


@dataclass(frozen=True)
class Played:
    lines: tuple[str, ...]
    writes: Writes
    outcomes: tuple[tuple[str, str], ...]
    errors: tuple[str, ...]
    interrupted: bool


def play(s: Root, task: Task, pinned: bool, finished: tuple[str, ...] = ()) -> Played:
    """The steps of a task that have no ok outcome yet, in order, and what the round prints of them."""
    lines: list[str] = []
    outcomes: list[tuple[str, str]] = []
    writes: list[tuple[str, tuple[str, ...]]] = []
    errors: list[str] = []
    failed = False
    for step in task.steps:
        if failed:
            outcomes.append((step.name, "skipped"))
            lines.append(f"skip {step.name}  0.0s")
            continue
        if step.name in finished:
            outcomes.append((step.name, "ok"))
            lines.append(f"ok   {step.name}  0.0s")
            continue
        effect = step.effect(s, pinned)
        writes.extend(effect.writes)
        if effect.interrupts:
            return Played((), tuple(writes), tuple(outcomes), (), True)
        if effect.error:
            failed = True
            errors.append(effect.error)
            outcomes.append((step.name, "failed"))
            lines.append(f"FAIL {step.name}  0.0s  {effect.error}")
        else:
            outcomes.append((step.name, "ok"))
            lines.append(f"ok   {step.name}  0.0s")
    if task.score is not None:
        lines += [task.score.headline, *task.score.detail]
    return Played(tuple(lines), tuple(writes), tuple(outcomes), tuple(errors), False)


def ledger_of(task: Task, played: Played, pinned: bool, segments: tuple[str, ...]) -> tuple[str, ...]:
    """The strings the ledger of a finished round holds."""
    caveats = [f"step '{name}' {status}" for name, status in played.outcomes if status != "ok"]
    if task.score is not None:
        caveats += task.score.caveats
    holds = ['"pinned": true' if pinned else '"pinned": false']
    holds += [f'"status": "{status}"' for _, status in played.outcomes]
    holds += [f'"outcome": "{outcome}"' for outcome in segments]
    holds += caveats or ['"caveats": []']
    return tuple(holds)


def score_of(task: Task) -> tuple[str, ...]:
    """The strings the score file of a finished round holds."""
    if task.score is None:
        return ("null",)
    return (f'"headline": "{task.score.headline}"', *(f'"{d}"' for d in task.score.detail), *(f'"{c}"' for c in task.score.caveats))
