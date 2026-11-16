"""The todo as the web app shows it: a record the todo API owns, and how the app's own list takes it in."""

from __future__ import annotations

from datetime import date
from typing import Any

from ostler.book import Create, Foreign, Needs, Transaction, View

from ..api.model.todo import TodoRecord as Stored
from .fixtures import Todo
from .model.todo import TodoRecord


def take(state: Any, ident: str, view: View) -> Transaction:
    due = view["due_on"]
    return Transaction(Create(state.todos, TodoRecord(ident, view["title"], None, date.fromisoformat(due) if due else None,
                                                      view["assignee"])))


TODO = Foreign(Stored, owner="services.api", reads=("title", "due_on", "assignee"), takes=take)


def standing(need: Needs) -> Todo:
    """The todo a user sees listed for a needed record, under the id the app issued."""
    return Todo.of(need.record, id=need.id)
