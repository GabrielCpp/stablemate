"""The todo API, as ostler loads it."""

import os
import sys

from ostler.book import App, Diverges, Environment, Process, Refusal, Refusals, Service, Stack

from . import fixtures
from .health import TheStoreAnswers
from .endpoints import ALL as ENDPOINTS, AddTodo, FindTodos, SetStore, UpdateTodo
from .journeys import ALL as JOURNEYS
from .model.lifecycle import MATRICES
from .model.state import Serving, TodoApp
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
