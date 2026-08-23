"""The frozen-app fixtures as a test sees them: the task modules loaded the way
`paddock.loader` loads them, and the apps that carry an answer key.

Each `test_<app>_app.py` loads its own task module the same way and keeps doing so — the
per-app files assert on things only that app has. What lives here is the part every one of
them repeated: the loader, and the list of apps a key-wide check parametrises over.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

from paddock.registry import REGISTRY

DATA = Path(__file__).parents[1]
APPS_DIR = DATA / "apps"

#: Every frozen app with an answer key — the set a key-wide check parametrises over. Derived
#: from the tree rather than listed, so a new fixture is checked the day it lands.
APPS: tuple[Path, ...] = tuple(
    sorted(p for p in APPS_DIR.iterdir() if (p / "defects.yml").is_file())
)


@contextlib.contextmanager
def tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def load_task(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    # The registry is module-global and a task module declares into it at import: reset it
    # around the load, exactly as `paddock.loader` does, or the second task loaded in this
    # process refuses on a name the first one claimed.
    REGISTRY.reset()
    with tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module
