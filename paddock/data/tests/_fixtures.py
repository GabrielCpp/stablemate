"""The frozen-app fixtures as a test sees them: the task modules loaded the way `paddock.loader` loads them, and the apps that carry an answer key."""

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
    REGISTRY.reset()
    with tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module
