# A worked example

This file shows one small product written as two books: a todo API, then a web app over it. Every file below is copied whole from a book ostler tests against a real app, so the code runs as written. Read it once before the first file of a new book, then follow the steps in SKILL.md with your own app. Write the files in this order: `model/`, `endpoints/` or `screens/`, `fixtures/`, `journeys/`, then `surface.py` and `service.py`, which collect the others.

The API book:

```
api/
  service.py            what ostler loads: stack, cast, refusals, diverges
  surface.py            credentials and the way the app is put back
  people.py             the accounts the API knows by name: `ANA = Actor("ana", fresh=...)`
  fixtures/todo.py      what a journey sends
  model/todo.py         the record and what a reader sees listed
  model/state.py        the states, and the rules that apply in each
  model/rules.py        why a request's content is refused
  model/actions.py      what each call does to the state
  model/lifecycle.py    the state x action matrices
  endpoints/shapes.py   the bodies, declared once
  endpoints/todos.py    one class per endpoint
  journeys/             one class per journey
```

The web book:

```
web/
  service.py            what ostler loads: stack, screens, interactions
  surface.py            the browser surface, 290 lines, left out here; screens.md and surface.md cover it
  fixtures/todo.py      what a user types: the API's `todo` factory without `remind_at`, `reminded` and `stranger`
  model/                the same record without its owner and reminder fields, its states and its actions
  screens/add_form.py   one screen: components, phases, transitions
  screens/labels.py     the words, one `T(en=..., fr=...)` each
  interactions.py       what a user does on a screen
  journeys/             one class per journey
```

The files this example leaves out follow the same shapes: `model/actions.py` and `model/lifecycle.py` are covered by [model.md](model.md) and [matrices-and-journeys.md](matrices-and-journeys.md), and the other endpoints, screens and journeys repeat the ones shown.

## The API book

### api/service.py

```python
"""The todo API, as ostler loads it."""

import os
import sys

from ostler.book import SOLE, App, Diverges, Environment, Process, Refusal, Refusals, Service, Stack

from . import fixtures
from .health import TheStoreAnswers
from .endpoints import ALL as ENDPOINTS, AddTodo, FindTodos, SetStore, UpdateTodo
from .journeys import ALL as JOURNEYS
from .model.lifecycle import MATRICES
from .model.state import Serving, TodoApp
from .people import ANA
from .surface import TodoApi

APP = os.path.join(os.path.dirname(__file__), "..", "..")
PORT = os.environ.get("TODO_API_PORT", "8080")


def stack(log_dir: str) -> Stack:
    return Stack((
        Process("api", [sys.executable, "app.py"], APP, "serving on",
                {"PORT": PORT, "TOKEN": "test-token", "API_KEY": "test-key"}),
    ), log_dir)


LOCAL = Environment("local", {"api": f"http://127.0.0.1:{PORT}"})

service = Service[TodoApp](
    name="api",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Serving,
    cast=(SOLE, ANA),
    surface=TodoApi,
    journeys=JOURNEYS,
    health=(TheStoreAnswers,),
    stack=stack,
    app=App(roots=("app.py",), verified="VERIFIED", ignore=()),
    endpoints=ENDPOINTS,
    matrices=MATRICES,
    watch=(FindTodos(),),
    refusals=Refusals(
        malformed=Refusal("Invalid JSON", 400),
        unknown_id=Refusal("Not found", 404),
        wrong_kind=Refusal("Not found", 404),
        missing=Refusal("Title is required", 400),
    ),
    diverges=(
        Diverges(AddTodo, "description wrong type", why="The app reads a description that is not a string as an empty one and saves the todo."),
        Diverges(UpdateTodo, "description wrong type", why="The app reads a description that is not a string as an empty one and saves the change."),
        Diverges(FindTodos, "assignee out of enum", why="The app takes an assignee it does not know as a filter that matches nothing and answers an empty list."),
        Diverges(SetStore, "down missing", why="The test hook reads a missing switch as false and brings the store back."),
        Diverges(SetStore, "down null", why="The test hook reads a null switch as false and brings the store back."),
    ),
    words={**{e.__name__: e for e in ENDPOINTS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)
```

### api/surface.py

```python
"""The API as a surface: ostler sends every step as declared; this keeps the
credentials and the way the app is put back to its first state."""

from __future__ import annotations

import json
from datetime import date

from ostler.book import Actor, ApiKey, Bearer, BookError, Client, Endpoint, Environment
from ostler.book.http import Reply
from ostler.book.httpsurface import HttpSurface

from .endpoints import ReadClock, Reset


class TodoApi(HttpSurface):
    def __init__(self, environment: Environment):
        super().__init__(Client(environment.address("api"), {Bearer(): "test-token", ApiKey(): "test-key"}))
        self.accounts: dict[Actor, dict[str, str]] = {}

    def restore(self) -> None:
        Reset().send(self.client)
        for actor in self.accounts:
            self.client.held.pop((actor, Bearer()), None)
        self.accounts = {}

    def send(self, call: Endpoint) -> Reply:
        if call.by is not None and call.by.fresh:
            self.account(call.by)
        return super().send(call)

    def account(self, actor: Actor) -> dict[str, str]:
        """What a person types to sign in as `actor`: the service makes the account the first time it is asked for, and the
        client holds the token that account signs in for."""
        if actor not in self.accounts:
            made = self.post("/admin/persons", {"handle": actor.handle})
            token = self.post("/sign-in", {"handle": made["handle"], "password": made["password"]})["token"]
            self.client.hold(actor, Bearer(), token)
            self.accounts[actor] = {"handle": made["handle"], "password": made["password"]}
        return self.accounts[actor]

    def post(self, path: str, body: dict[str, str]) -> dict[str, str]:
        status, raw = self.client.transport("POST", self.client.base + path, {"Content-Type": "application/json"},
                                            json.dumps(body).encode())
        if status not in (200, 201):
            raise BookError(f"POST {path} answered {status}: {raw.decode(errors='replace')}")
        return json.loads(raw)

    def today(self) -> date:
        return date.fromisoformat(ReadClock().send(self.client).body["today"])
```

### api/fixtures/todo.py

```python
"""A todo as a client sends it. `todo` is the base factory; every other function
is a variant that fills one thing in and passes the rest through, so a journey
composes the fixture it needs in one line and never writes an id: the service
assigns it when the todo is added, and the fixture learns it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from ostler.book import Fixture

TITLE_MAX = 120


@dataclass(eq=False)
class Todo(Fixture):
    title: str | None = None
    description: str | None = None
    due_on: date | str | None = None
    assignee: str | None = None
    remind_at: str | None = None
    id: str | None = None

    def __str__(self) -> str:
        return self.title if self.title and self.title.strip() else "(untitled)"


def todo(title: str = "Water the plants", **fields: Any) -> Todo:
    return Todo(title=title, **fields)


def scheduled(today: date, days: int = 1, **fields: Any) -> Todo:
    return todo(due_on=today + timedelta(days=days), **fields)


def past_due(today: date, days: int = 1, **fields: Any) -> Todo:
    return todo(due_on=today - timedelta(days=days), **fields)


def assigned(who: str, **fields: Any) -> Todo:
    return todo(assignee=who, **fields)


def reminded(at: str, **fields: Any) -> Todo:
    return todo(remind_at=at, **fields)


def described(text: str, **fields: Any) -> Todo:
    return todo(description=text, **fields)


def blank_title(**fields: Any) -> Todo:
    return todo(title="   ", **fields)


def too_long_title(**fields: Any) -> Todo:
    return todo(title="x" * (TITLE_MAX + 1), **fields)


def stranger(**fields: Any) -> Todo:
    """A todo nobody added: an id the service never issued."""
    return todo(title="Something nobody added", **fields).set(id=str(uuid4()))
```

### api/model/todo.py

```python
"""What the service keeps for one todo, and what a reader sees listed. Status is
never stored: it is read off the due date against the service's today."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ostler.book import Actor

USERS = ("ana", "bo")
STATUSES = ("unscheduled", "scheduled", "overdue")


@dataclass(frozen=True)
class TodoRecord:
    id: str
    title: str
    description: str | None
    due_on: date | None
    assignee: str | None
    remind_at: str | None = None
    remind_day: date | None = None
    owner: str | None = None

    def status(self, today: date) -> str:
        if self.due_on is None:
            return "unscheduled"
        return "scheduled" if self.due_on >= today else "overdue"

    def __str__(self) -> str:
        bits = [f"{self.title} [{self.id[:8]}]"]
        if self.due_on:
            bits.append(f"due {self.due_on.isoformat()}")
        if self.assignee:
            bits.append(f"for {self.assignee}")
        if self.description:
            bits.append(repr(self.description))
        return " · ".join(bits)


def owner_of(by: Actor | None) -> str | None:
    """The account a caller's todos belong to: a person's own handle, nobody for the shared credential."""
    return by.handle if by is not None and by.fresh else None


@dataclass(frozen=True)
class Day:
    today: date


@dataclass(frozen=True)
class Row:
    id: str
    title: str
    description: str | None
    due_on: str | None
    assignee: str | None
    status: str
    remind_at: str | None = None
    remind_day: str | None = None

    def __str__(self) -> str:
        bits = [self.title, self.status]
        if self.due_on:
            bits.append(f"due {self.due_on}")
        if self.assignee:
            bits.append(f"for {self.assignee}")
        if self.description:
            bits.append(repr(self.description))
        return " · ".join(bits)
```

### api/model/state.py

```python
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
        return tuple(self.row(t) for t in sorted((t for t in self.todos if t.owner is None), key=listing_order(self)))

    def key(self) -> Hashable:
        return (type(self).__name__, TodoApp.rows(self))

    def row(self, entity: object) -> Row:
        todo = cast(TodoRecord, entity)
        return Row(todo.id, todo.title, todo.description, todo.due_on.isoformat() if todo.due_on else None, todo.assignee,
                   todo.status(self.today), todo.remind_at, todo.remind_day.isoformat() if todo.remind_day else None)


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
```

### api/endpoints/shapes.py

```python
"""The bodies the API sends and accepts, each declared once."""

from ostler.book import Bool, Enum, Field, Id, Object, Str

from ..model.todo import STATUSES, USERS, TodoRecord

TODO = Object(
    "Todo",
    id=Field(Id(TodoRecord), does="assigned by the service, a UUID"),
    title=Field(Str(max_len=120)),
    description=Field(Str(max_len=2000), nullable=True),
    due_on=Field(Str(format="date"), nullable=True),
    assignee=Field(Enum(USERS), nullable=True),
    status=Field(Enum(STATUSES), does="read off due_on against the service's today"),
    created_at=Field(Str(format="date-time"), opaque="the service stamps its own clock and the model keeps no time of day"),
    remind_at=Field(Str(format="date-time"), nullable=True, does="echoed as written"),
    remind_day=Field(Str(format="date"), nullable=True, does="the day of the reminder, read off the date written in remind_at"),
)

TODO_INPUT = Object(
    "TodoInput",
    title=Field(Str(max_len=120), does="blank is refused"),
    description=Field(Str(max_len=2000), required=False, nullable=True, does="absent or null clears"),
    due_on=Field(Str(format="date"), required=False, nullable=True,
                 does="today or later; on an update the stored day may stay as it is; absent or null clears"),
    assignee=Field(Enum(USERS), required=False, nullable=True, does="absent or null clears"),
    remind_at=Field(Str(format="date-time"), required=False, nullable=True, does="an RFC 3339 date-time with an offset; absent or null clears"),
)

ERROR = Object("Error", error=Field(Str(), does="the reason, as a user reads it"))

CLOCK = Object("Clock", today=Field(Str(format="date")))

STORE = Object("Store", down=Field(Bool()))
```

### api/endpoints/todos.py

```python
"""The /todos endpoints. Each class is the whole contract of one endpoint and
has no method of its own: `send` comes from ostler and does what is declared.
`carries` names the model action the call carries; the state runs it."""

from ostler.book import Answer, ApiKey, Bearer, Endpoint, Enum, Field, Id, List, Object, Str

from .shapes import ERROR, TODO, TODO_INPUT
from ..model import actions
from ..model.lists import TODOS
from ..model.todo import STATUSES, USERS, TodoRecord

CREDENTIALS = (Bearer(), ApiKey())
NO_CREDENTIAL = Answer(401, ERROR, "no accepted credential")
STORE_DOWN = Answer(503, ERROR, "the store is down; nothing was written or read",
                    why="The app cannot tell a saved todo from a lost one while the store is away, so it answers nothing rather than something false.")
NOT_FOUND = Answer(404, ERROR, "no todo has this id, or it was removed")
MAIN = "app.py::"
BY_ID = Object(id=Field(Id(TodoRecord), does="the todo's id"))


class AddTodo(Endpoint):
    method = "POST"
    path = "/todos"
    auth = CREDENTIALS
    body = TODO_INPUT
    answers = (
        Answer(201, TODO, "created; the id and the derived status come back", creates="id"),
        Answer(400, ERROR, "a field rule is broken: the first one, in field order"),
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "create_todo", MAIN + "parse_fields", MAIN + "todos_handler")
    does = "Creates one todo; the service assigns its id. Two identical posts make two todos."
    carries = actions.AddTodo


class ReadTodo(Endpoint):
    method = "GET"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    answers = (Answer(200, TODO, "the todo, with its status as of the service's today"), NOT_FOUND, NO_CREDENTIAL, STORE_DOWN)
    source = (MAIN + "todos_handler", MAIN + "find", MAIN + "view")
    does = "Reads one todo."
    carries = actions.ReadTodo


class UpdateTodo(Endpoint):
    method = "PUT"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    body = TODO_INPUT
    answers = (
        Answer(200, TODO, "the todo after the change"),
        Answer(400, ERROR, "a field rule is broken; nothing changed"),
        NOT_FOUND,
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "put_todo", MAIN + "parse_fields", MAIN + "todos_handler")
    does = "Replaces the whole todo with the body sent; a field left out is cleared."
    carries = actions.ReplaceTodo


class RemoveTodo(Endpoint):
    method = "DELETE"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = BY_ID
    answers = (Answer(204, None, "removed; the id never resolves again"), NOT_FOUND, NO_CREDENTIAL, STORE_DOWN)
    source = (MAIN + "todos_handler", MAIN + "find")
    does = "Removes one todo."
    carries = actions.RemoveTodo


class FindTodos(Endpoint):
    method = "GET"
    path = "/todos"
    auth = CREDENTIALS
    query = Object(
        text=Field(Str(), required=False, does="matches title or description, case folded"),
        assignee=Field(Enum(USERS), required=False, does="an unknown assignee matches nothing"),
        status=Field(Enum(STATUSES), required=False),
    )
    answers = (
        Answer(200, List(TODO, entries=TODOS), "the matches: overdue soonest first, then scheduled soonest first, then unscheduled newest first"),
        Answer(400, ERROR, "status is not one of the three"),
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    source = (MAIN + "list_todos", MAIN + "order", MAIN + "todos_handler")
    does = "Lists todos, all of them or the ones matching every filter sent."
    carries = actions.FindTodos
```

### api/journeys/a_week_of_chores.py

```python
from datetime import date, timedelta

from ostler.book import Journey, Listed, Relates, Same

from ..endpoints import AddTodo, FindTodos, ReadTodo, RemoveTodo, UpdateTodo
from ..fixtures import Query, scheduled, todo


class AWeekOfChores(Journey):
    """Ana plans her week. She writes down three chores, one with no date yet,
    hands one to Bo, finishes one and crosses it off, renames another, and moves
    the first one's due date back a day. Then she looks at what is left for her."""

    def steps(self, today: date):
        milk = scheduled(today, 1, title="Buy milk", assignee="ana")
        plumber = scheduled(today, 2, title="Call the plumber", description="The kitchen tap drips", assignee="ana",
                        remind_at=f"{today + timedelta(days=1)}T08:00:00+00:00")
        photos = todo("Sort the photos")
        yield AddTodo(milk)
        yield AddTodo(plumber)
        yield AddTodo(photos)
        yield Listed(milk, plumber, photos)
        yield UpdateTodo(plumber.set(assignee="bo"))
        yield RemoveTodo(milk)
        yield UpdateTodo(photos.set(title="Sort the holiday photos"))
        yield UpdateTodo(plumber.set(due_on=today + timedelta(days=4)))
        yield Listed(plumber, photos)
        yield ReadTodo(plumber)
        yield FindTodos(query=Query(assignee="ana"))
        yield FindTodos(query=Query(text="plumber"))
        yield FindTodos(query=Query(status="unscheduled"))
        first, again = FindTodos(), FindTodos()
        yield first
        yield again
        yield Same(first, again)
        one = ReadTodo(plumber)
        yield one
        yield Relates("the todo read back is the todo listed", (one, first), lambda read, found: None if read.body["title"] in [t["title"] for t in found.body] else f"{read.body['title']} is not in the list")
```

## The web book

The web book names the API book's `ANA` as its person. It declares screens and interactions and no endpoints.

### web/service.py

```python
"""The todo web app, as ostler loads it."""

import os
import sys

from ostler.book import Because, Environment, Person, Process, Service, Stack, Unseen

from . import fixtures
from ..api.people import ANA
from .interactions import ALL as INTERACTIONS
from .journeys import ALL as JOURNEYS
from .model.lifecycle import MATRICES
from .model.rules import unknown_status
from .model.state import Online, TodoApp
from .screens import ALL as SCREENS
from .surface import TodoWeb

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
API_PORT = os.environ.get("TODO_API_PORT", "8080")
WEB_PORT = os.environ.get("TODO_WEB_PORT", "8081")
API = f"http://127.0.0.1:{API_PORT}"


def stack(log_dir: str) -> Stack:
    return Stack((
        Process("api", [sys.executable, "app.py"], ROOT, "serving on",
                {"PORT": API_PORT, "TOKEN": "test-token", "API_KEY": "test-key"}),
        Process("web", [sys.executable, "serve.py"], os.path.join(ROOT, "web"), "serving on",
                {"PORT": WEB_PORT, "API_URL": API}),
    ), log_dir)


LOCAL = Environment("local", {"api": API, "web": f"http://127.0.0.1:{WEB_PORT}"})

service = Service[TodoApp](
    name="web",
    environments={"local": LOCAL},
    default_environment="local",
    languages=("en", "fr"),
    person=Person("services.api", ANA),
    new_model=Online,
    surface=TodoWeb,
    journeys=JOURNEYS,
    stack=stack,
    screens=SCREENS,
    interactions=INTERACTIONS,
    matrices=MATRICES,
    unseen=(Unseen(unknown_status, Because.OUTSIDE, "the page offers only the known statuses, so only a hand-written address draws the refusal"),),
    words={**{i.__name__: i for i in INTERACTIONS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)
```

### web/screens/add_form.py

```python
"""The form above the list. One todo per Save; the fields clear when it lands."""

from ostler.book import Field as Wire, Phase, Screen, Str, Stored, T, Transition, When, request
from ostler.book.screen import Button, DateField, Field, Select, Spinner, Text, TextArea

from .labels import ASSIGNEE, DESCRIPTION, DUE, SAVE, TITLE
from .list_page import ListPage
from .users import FORM, RECEIVED

form = Text("add-form", does="the form element, role=form")
title = Field(None, TITLE, takes="title", holds=Wire(Str(max_len=120)))
description = TextArea("todo-description", DESCRIPTION, takes="description",
                       holds=Wire(Str(max_len=2000), required=False, nullable=True))
due = DateField("todo-due", DUE, takes="due_on", holds=Wire(Str(format="date"), required=False))
assignee = Select(None, ASSIGNEE, lists=FORM)
save = Button(None, SAVE, "POST /todos with the non-empty fields")
saving = Spinner("todo-saving", "the request is out")
error = Text("todo-error", does="the API's error text, role=alert")

idle = Phase("idle", hides=(saving, error), because="Save is enabled only when the title is not blank")
saving_phase = Phase("saving", shows=(saving,), disabled=(title, description, due, assignee, save))
refused = Phase("refused", shows=(error,), because="the fields keep what was typed")


class AddForm(Screen):
    source = ("web/index.html", "web/app.js")
    api = "/todos"
    sends = (request("POST", "/todos"), RECEIVED)
    name = T(en="Add a todo", fr="Ajouter une tâche")
    inside = ListPage
    root = form
    title = title
    description = description
    due = due
    assignee = assignee
    save = save
    saving = saving
    error = error

    stored = (
        Stored("title", "any text; Save needs it non-blank", '""'),
        Stored("description", "any text", '""'),
        Stored("due", "YYYY-MM-DD or empty", '""'),
        Stored("assignee", '"" | "ana" | "bo"', '""'),
        Stored("phase", "idle | saving | refused", "idle"),
        Stored("error", "the last refusal's message, or empty", '""'),
    )
    phases = (idle, saving_phase, refused)
    transitions = (
        Transition(idle, When("click", save), saving_phase, only_if="title is not blank and online"),
        Transition(saving_phase, When("201"), idle, then="fields cleared; list refetched"),
        Transition(saving_phase, When("4xx or 5xx"), refused, then="error = body.error; fields kept"),
        Transition(saving_phase, When("network error"), refused, then="error = a generic message"),
        Transition(refused, When("edit any field"), idle, then="error hidden"),
        Transition(refused, When("click", save), saving_phase, only_if="title is not blank"),
    )
```

### web/journeys/save_twice_makes_one_todo.py

```python
from datetime import date

from ostler.book import Check, Journey, Listed

from ..fixtures import assigned
from ..interactions import AddTodo


class SaveTwiceMakesOneTodo(Journey):
    """Ana types a chore and, impatient, presses Save a second time while the
    first request is out. One todo lands, because Save is disabled while
    saving."""

    def steps(self, today: date):
        cat = assigned("ana", title="Feed the cat")
        yield AddTodo(cat)
        yield Check("Save is disabled while saving and the form is clear after",
                    lambda s: s.save_was_disabled_while_saving("Feed the cat again"))
        yield Listed(cat)
```
