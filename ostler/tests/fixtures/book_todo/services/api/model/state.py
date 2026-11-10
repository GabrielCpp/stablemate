"""The states the todo API can be in. Both keep the same todos; they differ in
what they refuse. `Serving` turns away only a call with no credential.
`StoreDown` also turns away every call that would reach the store."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Generic, Hashable, TypeVar, cast

from ostler.book import Action, Actor, Collection, Endpoint, Rule, State, Unique, Index

from .todo import Row, TodoRecord

A = TypeVar("A")


class TodoApp(State):
    todos = Collection(TodoRecord, Unique("id"), Index("assignee"))

    def rows(self) -> tuple[Row, ...]:
        return tuple(self.row(t) for t in sorted(self.todos, key=listing_order(self)))

    def key(self) -> Hashable:
        return (type(self).__name__, TodoApp.rows(self))

    def row(self, entity: object) -> Row:
        todo = cast(TodoRecord, entity)
        return Row(todo.id, todo.title, todo.description, todo.due_on.isoformat() if todo.due_on else None, todo.assignee,
                   todo.status(self.today))


class StoreAction(Action[A, TodoApp], Generic[A]):
    """An action that reads or writes the store, and so is refused while it is down."""


def listing_order(s: TodoApp) -> Callable[[TodoRecord], tuple[int, date, int]]:
    """Overdue soonest first, then scheduled soonest first, then unscheduled newest first."""

    def key(todo: TodoRecord) -> tuple[int, date, int]:
        position = s.todos.position(todo.id)
        if todo.due_on is None:
            return (2, date.min, -position)
        return (0 if todo.due_on < s.today else 1, todo.due_on, position)

    return key


def _reaches_the_store(call: Endpoint, s: TodoApp, by: Actor | None) -> bool:
    carried: type[Action[Any, Any]] | None = type(call).carries
    return carried is not None and issubclass(carried, StoreAction)


UNAUTHORIZED = Rule[Endpoint, TodoApp]("Unauthorized", lambda call, s, by: bool(type(call).auth) and by is None, 401)
SERVICE_UNAVAILABLE = Rule[Endpoint, TodoApp]("Service unavailable", _reaches_the_store, 503)


class Serving(TodoApp):
    rules = (UNAUTHORIZED,)


class StoreDown(TodoApp):
    rules = (UNAUTHORIZED, SERVICE_UNAVAILABLE)

    def rows(self) -> tuple[Row, ...]:
        return ()
