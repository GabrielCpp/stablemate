"""What the web app does to its list. Each action says what it accepts, which
rules it checks in that order, and what it reduces to on the state: a
transaction of primitives for a write, a selection for a filter, a new state
for a change around the app."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from ostler.book import Action, Actor, Become, Create, Delete, MoveToday, Select, Transaction, Update

from ..fixtures import Clock, Network, Query, Switch, Todo
from . import rules
from .state import Hold, Offline, Online, Refresh, StoreAction, StoreDown, TodoApp, listing_order
from .todo import TodoRecord


def record(a: Todo) -> TodoRecord:
    """The record the app lists for the todo a user saved; the id is already set."""
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


class Add(StoreAction[Todo]):
    accept = Todo
    rules = rules.FIELD_RULES

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))


class Edit(StoreAction[Todo]):
    accept = Todo
    rules = (rules.not_found, *rules.FIELD_RULES)

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(Update(s.todos, a.id, record(a)))


class Remove(StoreAction[Todo]):
    accept = Todo
    rules = (rules.not_found,)

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(Delete(s.todos, a.id))


class Find(StoreAction[Query]):
    accept = Query
    rules = (rules.unknown_status,)

    @staticmethod
    def reduce(a: Query, s: TodoApp, by: Actor | None) -> Select[TodoRecord]:
        return Select(s.todos, where=matches(a, s.today), order=listing_order(s))


class MoveClock(Action[Clock, TodoApp]):
    accept = Clock
    rules = (rules.clock_must_be_a_date,)

    @staticmethod
    def reduce(a: Clock, s: TodoApp, by: Actor | None) -> Transaction:
        return Transaction(Hold() if isinstance(s, StoreDown) else Refresh(), MoveToday(rules.as_date(a.today)))


class SwitchStore(Action[Switch, TodoApp]):
    accept = Switch

    @staticmethod
    def reduce(a: Switch, s: TodoApp, by: Actor | None) -> Become:
        return Become(StoreDown if a.down else Online)


class SwitchNetwork(Action[Network, TodoApp]):
    accept = Network

    @staticmethod
    def reduce(a: Network, s: TodoApp, by: Actor | None) -> Transaction:
        if a.offline:
            return Transaction(Become(Offline))
        return Transaction(Become(Online), Refresh())
