"""Why the API says no to a request's content. The message is the one the
service sends, word for word. A rule reads the request (`a`) and the state (`s`)."""

from __future__ import annotations

from datetime import date

from ostler.book import Actor, Rule

from ..fixtures import Clock, Query, Todo
from ..fixtures.todo import TITLE_MAX
from .state import TodoApp
from .todo import STATUSES, USERS

DESCRIPTION_MAX = 2000


def parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _due_moved_into_the_past(a: Todo, s: TodoApp, by: Actor | None) -> bool:
    due = parse_date(a.due_on) if a.due_on is not None else None
    if due is None or due >= s.today:
        return False
    kept = a.id in s.todos and s.todos[a.id].due_on == due
    return not kept


title_required = Rule[Todo, TodoApp]("Title is required", lambda a, s, by: not isinstance(a.title, str) or not a.title.strip())
title_too_long = Rule[Todo, TodoApp]("Title is too long", lambda a, s, by: a.title is not None and len(a.title.strip()) > TITLE_MAX)
description_too_long = Rule[Todo, TodoApp]("Description is too long",
                                           lambda a, s, by: a.description is not None and len(a.description) > DESCRIPTION_MAX)
due_must_be_a_date = Rule[Todo, TodoApp]("Due date must be a date", lambda a, s, by: a.due_on is not None and parse_date(a.due_on) is None)
due_not_in_the_past = Rule[Todo, TodoApp]("Due date cannot be in the past", _due_moved_into_the_past,
                                         why="A chore due yesterday would show as overdue the moment it is written, so the app refuses it; a date already past is kept only when it is left unchanged.")
no_such_user = Rule[Todo, TodoApp]("No such user", lambda a, s, by: a.assignee is not None and a.assignee not in USERS)
not_found = Rule[Todo, TodoApp]("Not found", lambda a, s, by: a.id not in s.todos, 404)
unknown_status = Rule[Query, TodoApp]("Unknown status", lambda a, s, by: a.status is not None and a.status not in STATUSES)
clock_must_be_a_date = Rule[Clock, TodoApp]("Due date must be a date", lambda a, s, by: parse_date(a.today) is None)

FIELD_RULES = (title_required, title_too_long, description_too_long, due_must_be_a_date, due_not_in_the_past, no_such_user)
