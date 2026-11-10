"""The lifecycle matrices: one for a chore, one for the app itself. Each scene
names its condition and the calls that reach it; each action aims one call at
the record there, or builds none where the pair cannot occur."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, cast

from ostler.book import Axes, Impossible, Scene

from ..endpoints import AddTodo, FindTodos, ReadClock, ReadTodo, RemoveTodo, Reset, SetClock, SetStore, UpdateTodo
from ..fixtures import Clock, Switch, Todo, scheduled, todo
from .state import TodoApp
from .todo import TodoRecord

TODAY = date(2026, 11, 4)
CHORE = "Fix the gate"


def chore_of(model: TodoApp) -> TodoRecord | None:
    """The chore the scene is about: the first todo kept, whatever it is called now."""
    return next(iter(model.todos), None)


def _on_chore(build: Callable[[TodoApp, Todo], object]) -> Callable[[TodoApp], object]:
    def aim(model: TodoApp) -> object:
        chore = chore_of(model)
        return build(model, Todo.of(chore)) if chore else Impossible("no todo is listed to aim at")

    return aim


CHORE_SCENES = (
    Scene("(none)", "no todo is listed", lambda today: ()),
    Scene("unscheduled", f"{CHORE!r} is listed with no due day", lambda today: (AddTodo(todo(CHORE)),)),
    Scene("scheduled", f"{CHORE!r} is listed with a due day on or after today",
          lambda today: (AddTodo(scheduled(today, 2, title=CHORE)),)),
    Scene("overdue", f"{CHORE!r} is listed with a due day before today",
          lambda today: (AddTodo(scheduled(today, 2, title=CHORE)), SetClock(Clock(today + timedelta(days=3))))),
)

def _day_after_the_chore(model: TodoApp) -> SetClock | Impossible:
    chore = chore_of(model)
    if chore is None:
        return Impossible("no todo is listed, so no due day can pass")
    if chore.due_on is None:
        return Impossible("a todo with no due day has none to pass")
    return SetClock(Clock(chore.due_on + timedelta(days=1)))


CHORE_ACTIONS: dict[str, Callable[[TodoApp], object]] = {
    "add": lambda m: AddTodo(todo(CHORE)),
    "update title": _on_chore(lambda m, c: UpdateTodo(c.set(title="Mend the gate"))),
    "update due to a future day": _on_chore(lambda m, c: UpdateTodo(c.set(due_on=m.today + timedelta(days=5)))),
    "update due to a past day": _on_chore(lambda m, c: UpdateTodo(c.set(due_on=m.today - timedelta(days=1)))),
    "clear due": _on_chore(lambda m, c: UpdateTodo(c.set(due_on=None))),
    "read": _on_chore(lambda m, c: ReadTodo(c)),
    "remove": _on_chore(lambda m, c: RemoveTodo(c)),
    "on: the due day passes": _day_after_the_chore,
}


def chore_status(model: TodoApp) -> str:
    chore = chore_of(model)
    return chore.status(model.today) if chore else "(none)"


APP_SCENES = (
    Scene("Serving", "every call with a credential reaches the store", lambda today: ()),
    Scene("StoreDown", "a call that would reach the store is turned away with 503", lambda today: (SetStore(Switch(down=True)),)),
)

APP_ACTIONS: dict[str, Callable[[TodoApp], object]] = {
    "add": lambda m: AddTodo(todo(CHORE)),
    "list": lambda m: FindTodos(),
    "read the clock": lambda m: ReadClock(),
    "move the clock": lambda m: SetClock(Clock(m.today + timedelta(days=1))),
    "take the store down": lambda m: SetStore(Switch(down=True)),
    "bring the store back": lambda m: SetStore(Switch(down=False)),
    "reset": lambda m: Reset(),
}

MATRICES = (
    Axes[TodoApp]("chore", TODAY, CHORE_SCENES, CHORE_ACTIONS, chore_status,
                  state_of=lambda m, t: cast(TodoRecord, t).status(m.today), entities=lambda m: m.todos),
    Axes[TodoApp]("app", TODAY, APP_SCENES, APP_ACTIONS, lambda m: type(m).__name__,
                  state_of=lambda m, _: type(m).__name__),
)
