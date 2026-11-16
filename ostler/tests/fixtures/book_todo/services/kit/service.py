"""The SvelteKit app, as ostler loads it."""

import os
import shutil
import sys

from ostler.book import Environment, Process, Service, Stack

from ..web.service import API, API_PORT, ROOT
from .interactions import ALL as INTERACTIONS
from .journeys import ALL as JOURNEYS
from .model import KitApp
from .screens import ALL as SCREENS
from .surface import KitWeb

KIT_PORT = os.environ.get("TODO_KIT_PORT", "8082")
KIT = f"http://127.0.0.1:{KIT_PORT}"


def stack(log_dir: str) -> Stack:
    return Stack((
        Process("api", [sys.executable, "app.py"], ROOT, "serving on",
                {"PORT": API_PORT, "TOKEN": "test-token", "API_KEY": "test-key"}),
        Process("kit", [shutil.which("node") or "node", "build/index.js"], os.path.join(ROOT, "kit"), "Listening on",
                {"PORT": KIT_PORT, "HOST": "127.0.0.1", "ORIGIN": KIT, "TODO_API": API}),
    ), log_dir)


LOCAL = Environment("local", {"api": API, "kit": KIT})

service = Service[KitApp](
    name="kit",
    environments={"local": LOCAL},
    default_environment="local",
    languages=("en", "fr"),
    new_model=KitApp,
    surface=KitWeb,
    journeys=JOURNEYS,
    stack=stack,
    screens=SCREENS,
    interactions=INTERACTIONS,
    words={i.__name__: i for i in INTERACTIONS},
)
