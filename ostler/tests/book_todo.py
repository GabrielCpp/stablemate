"""The todo book of `fixtures/book_todo`, loaded the way an author's repo loads it, and a runner that plays it against the stand-in app."""

from __future__ import annotations

import contextlib
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator
from types import ModuleType

FIXTURE = Path(__file__).parent / "fixtures" / "book_todo"


def module(name: str) -> ModuleType:
    """A module of the fixture book, with the fixture's root on the import path."""
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    return importlib.import_module(name)


def runtime(port: int, web: int | None = None, digest: int | None = None, kit: int | None = None) -> dict[str, str]:
    """The environment a book run gets: the port the stand-in app listens on, the port of its web page and of
    the digest service and of the kit app when there are ones, and no import path."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["TODO_API_PORT"] = str(port)
    if web is not None:
        env["TODO_WEB_PORT"] = str(web)
    if digest is not None:
        env["TODO_DIGEST_PORT"] = str(digest)
    if kit is not None:
        env["TODO_KIT_PORT"] = str(kit)
    return env


def run_book(arguments: list[str], port: int, cwd: Path = FIXTURE, web: int | None = None,
             digest: int | None = None, kit: int | None = None) -> subprocess.CompletedProcess[str]:
    """`python -m ostler.book` from the fixture's root, with the app on `port`, its page on `web`, the digest service on `digest` and the kit app on `kit`."""
    return subprocess.run([sys.executable, "-m", "ostler.book", *arguments], cwd=cwd, env=runtime(port, web, digest, kit),
                          capture_output=True, text=True, check=False)


@contextlib.contextmanager
def services_from(path: Path) -> Iterator[None]:
    """The `services` package of the books under `path` in place of any loaded one, put back on leaving."""
    def loaded() -> dict[str, ModuleType]:
        return {name: held for name, held in sys.modules.items() if name == "services" or name.startswith("services.")}

    saved = loaded()
    for name in saved:
        del sys.modules[name]
    sys.path.insert(0, str(path))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path.remove(str(path))
        for name in loaded():
            del sys.modules[name]
        sys.modules.update(saved)
