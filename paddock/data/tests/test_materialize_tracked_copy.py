"""`materialize` copies what git tracks under the app, not "everything except a denylist"."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

DATA = Path(__file__).parents[1]


@contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load_frozenapp() -> ModuleType:
    path = DATA / "tasks" / "_frozenapp.py"
    spec = importlib.util.spec_from_file_location("_frozenapp", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        sys.modules["_frozenapp"] = module
        spec.loader.exec_module(module)
    return module


frozenapp = _load_frozenapp()


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _build_app(tmp_path: Path) -> Path:
    """A minimal app fixture: one tracked file, a nested untracked artifact beside it."""
    app = tmp_path / "app"
    (app / "docs" / "specs" / "only-story").mkdir(parents=True)
    (app / "docs" / "specs" / "only-story" / "spec.md").write_text("spec\n", encoding="utf-8")
    (app / "stories" / "only-story").mkdir(parents=True)
    (app / "stories" / "only-story" / "diff.yml").write_text(
        "changed: []\nadded: []\npinned: []\n", encoding="utf-8"
    )
    (app / "sub").mkdir()
    (app / "sub" / "tracked.txt").write_text("tracked\n", encoding="utf-8")

    _git("init", "--quiet", "--initial-branch", "main", cwd=app)
    _git("add", "--all", cwd=app)
    _git("commit", "--quiet", "-m", "app", cwd=app)

    artifact = app / "sub" / ".venv" / "bin"
    artifact.mkdir(parents=True)
    (artifact / "python").write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    return app


def test_materialize_carries_tracked_files_but_not_a_nested_untracked_artifact(
    tmp_path: Path,
) -> None:
    app = _build_app(tmp_path)

    dest = frozenapp.materialize(app, "only-story", tmp_path / "dest")

    assert (dest / "sub" / "tracked.txt").is_file()
    assert not (dest / "sub" / ".venv").exists()
