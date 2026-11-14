"""The digest, as ostler loads it: a service that stores nothing and answers from the todo API."""

import os
import sys

from ostler.book import App, Environment, Process, Service, Stack

from .endpoints import ReadDigest, ReadDigestEntry
from .journeys import ALL as JOURNEYS
from .model import Digesting
from .surface import DigestApi

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
API_PORT = os.environ.get("TODO_API_PORT", "8080")
DIGEST_PORT = os.environ.get("TODO_DIGEST_PORT", "8082")
API = f"http://127.0.0.1:{API_PORT}"


def stack(log_dir: str) -> Stack:
    return Stack((
        Process("api", [sys.executable, "app.py"], ROOT, "serving on",
                {"PORT": API_PORT, "TOKEN": "test-token", "API_KEY": "test-key"}),
        Process("digest", [sys.executable, "app.py"], os.path.join(ROOT, "digest"), "serving on",
                {"PORT": DIGEST_PORT, "TODO_URL": API, "BUG": os.environ.get("TODO_DIGEST_BUG", "")}),
    ), log_dir)


LOCAL = Environment("local", {"api": API, "digest": f"http://127.0.0.1:{DIGEST_PORT}"})

service = Service[Digesting](
    name="digest",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Digesting,
    surface=DigestApi,
    journeys=JOURNEYS,
    stack=stack,
    app=App(roots=("digest",), verified="VERIFIED", ignore=()),
    endpoints=(ReadDigest, ReadDigestEntry),
    words={"ReadDigest": ReadDigest, "ReadDigestEntry": ReadDigestEntry},
)
