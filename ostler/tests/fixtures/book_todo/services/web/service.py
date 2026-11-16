"""The todo web app, as ostler loads it."""

import os
import sys

from ostler.book import Environment, Person, Process, Service, Stack

from . import fixtures
from ..api.people import ANA
from .interactions import ALL as INTERACTIONS
from .journeys import ALL as JOURNEYS
from .model.lifecycle import MATRICES
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
    words={**{i.__name__: i for i in INTERACTIONS}, **{name: getattr(fixtures, name) for name in fixtures.__all__}},
)
