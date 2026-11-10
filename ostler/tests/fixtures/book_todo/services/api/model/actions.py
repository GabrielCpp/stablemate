"""What the todo API does. Each action says what it accepts, which rules it
checks in that order, and what it reduces to on the state: a transaction of
primitives for a write, a selection for a read."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from ostler.book import Action, Actor, Become, Create, Delete, MoveToday, Select, Show, Transaction, Update

from ..fixtures import Clock, Query, Switch, Todo
from . import rules
from .state import Serving, StoreAction, StoreDown, TodoApp, listing_order
from .todo import Day, TodoRecord


def record(a: Todo) -> TodoRecord:
    """The record the service keeps for the todo a client sent; the id is already set."""
    assert a.id is not None
    due = rules.as_date(a.due_on) if a.due_on is not None else None
    return TodoRecord(a.id, (a.title or "").strip(), a.description, due, a.assignee)


def matches(q: Query, today: date):
    def keep(t: TodoRecord) -> bool:
        if q.text is not None:
            text = q.text.casefold()
            if text not in t.title.casefold() and text not in (t.description or "").casefold():
                return False
        if q.assignee is not None and t.assignee != q.assignee:
            return False
        return q.status is None or t.status(today) == q.status

    return keep


class AddTodo(StoreAction[Todo]):
    accept = Todo
    rules = rules.FIELD_RULES

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))


class ReadTodo(StoreAction[Todo]):
    accept = Todo
    rules = (rules.not_found,)

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Select[TodoRecord]:
        return Select(s.todos, where=lambda t: t.id == a.id)


class ReplaceTodo(StoreAction[Todo]):
    accept = Todo
    rules = (rules.not_found, *rules.FIELD_RULES)

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(Update(s.todos, a.id, record(a)))


class RemoveTodo(StoreAction[Todo]):
    accept = Todo
    rules = (rules.not_found,)

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(Delete(s.todos, a.id))


class FindTodos(StoreAction[Query]):
    accept = Query
    rules = (rules.unknown_status,)

    @staticmethod
    def reduce(a: Query, s: TodoApp, by: Actor | None) -> Select[TodoRecord]:
        return Select(s.todos, where=matches(a, s.today), order=listing_order(s))


class TellDay(Action[object, TodoApp]):
    @staticmethod
    def reduce(a: object, s: TodoApp, by: Actor | None) -> Show:
        return Show(Day(s.today))


class MoveClock(Action[Clock, TodoApp]):
    accept = Clock
    rules = (rules.clock_must_be_a_date,)

    @staticmethod
    def reduce(a: Clock, s: TodoApp, by: Actor | None) -> MoveToday:
        return MoveToday(rules.as_date(a.today))


class SwitchStore(Action[Switch, TodoApp]):
    accept = Switch

    @staticmethod
    def reduce(a: Switch, s: TodoApp, by: Actor | None) -> Become:
        return Become(StoreDown if a.down else Serving)


class Wipe(Action[object, TodoApp]):
    @staticmethod
    def reduce(a: object, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(*(Delete(s.todos, t.id) for t in s.todos), MoveToday(datetime.now(timezone.utc).date()), Become(Serving))
