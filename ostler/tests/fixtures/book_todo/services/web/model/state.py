"""The states the web app can be in. All three list the same todos; they differ
in what they refuse. `Online` refuses nothing of its own. `Offline` turns away
every act that would reach the store, with the banner's words. `StoreDown`
turns the same acts away with the API's words."""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any, Callable, Generic, TypeVar, cast

from ostler.book import Action, Actor, Change, Collection, Index, Interaction, Rule, State, Unique

from .todo import Row, TodoRecord

A = TypeVar("A")


class TodoApp(State):
    todos = Collection(TodoRecord, Unique("id"), Index("assignee"))

    frozen: tuple[Row, ...] | None = None

    def rows(self) -> tuple[Row, ...]:
        if self.frozen is not None:
            return self.frozen
        return self.listed()

    def listed(self) -> tuple[Row, ...]:
        return tuple(self.row(t) for t in sorted(self.todos, key=listing_order(self)))

    def apply(self, request: object) -> tuple[object, ...] | None:
        shown = super().apply(request)
        carried = getattr(type(request), "carries", None)
        if carried is not None and issubclass(carried, StoreAction):
            self.frozen = None
        return shown

    def row(self, entity: object) -> Row:
        todo = cast(TodoRecord, entity)
        return Row(todo.title, todo.due_on.isoformat() if todo.due_on else None, todo.assignee, todo.status(self.today))


class StoreAction(Action[A, TodoApp], Generic[A]):
    """An action that reads or writes the store behind the app, and so is refused
    while the network is off or the store is down."""


@dataclasses.dataclass(frozen=True, eq=False)
class Hold(Change):
    """The page was opened while the store was down: the list stays what that
    open could show, nothing."""

    def apply(self, state: State) -> None:
        assert isinstance(state, TodoApp)
        state.frozen = ()

    def __str__(self) -> str:
        return "the list stays as the app shows it"

    def brief(self) -> str:
        return "the list is held"


@dataclasses.dataclass(frozen=True, eq=False)
class Refresh(Change):
    """The app fetched the list again, so it shows the store as it is."""

    def apply(self, state: State) -> None:
        assert isinstance(state, TodoApp)
        state.frozen = None

    def __str__(self) -> str:
        return "the list is fetched again"

    def brief(self) -> str:
        return "the list is fetched"


def listing_order(s: TodoApp) -> Callable[[TodoRecord], tuple[int, date, int]]:
    """Overdue soonest first, then scheduled soonest first, then unscheduled newest first."""

    def key(todo: TodoRecord) -> tuple[int, date, int]:
        position = s.todos.position(todo.id)
        if todo.due_on is None:
            return (2, date.min, -position)
        return (0 if todo.due_on < s.today else 1, todo.due_on, position)

    return key


def _reaches_the_store(act: Interaction[Any], s: TodoApp, by: Actor | None) -> bool:
    carried: type[Action[Any, Any]] | None = type(act).carries
    return carried is not None and issubclass(carried, StoreAction)


OFFLINE = Rule[Interaction[Any], TodoApp]("You're offline", _reaches_the_store, 0)
SERVICE_UNAVAILABLE = Rule[Interaction[Any], TodoApp]("Service unavailable", _reaches_the_store, 503)


class Online(TodoApp):
    rules = ()


class Offline(TodoApp):
    rules = (OFFLINE,)


class StoreDown(TodoApp):
    rules = (SERVICE_UNAVAILABLE,)
