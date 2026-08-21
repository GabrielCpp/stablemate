"""Tests for `_stablemate` — the process boundary a paddock task drives stablemate across.

The property both tests protect is the same one: a pinned round runs the pinned tree's
code and reads the pinned tree's paths. It broke once invisibly — `uv run --project`
against the workspace anchor installs none of the tools, so the command fell back to
`$PATH`, where an editable install resolved every workflow module to the operator's live
tree, straight through the pin. Nothing failed; the round just measured the wrong code.
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

from paddock.registry import REGISTRY

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


sm = _load("_stablemate", DATA / "tasks" / "_stablemate.py")


def test_uv_run_names_the_member_environment() -> None:
    """The prefix must carry `--package`, or the tool comes off `$PATH` — the live tree."""
    assert sm.uv_run(Path("/x/checkout"), "workhorse-workflows") == [
        "uv", "run", "--project", "/x/checkout", "--package", "workhorse-workflows",
    ]


def test_pin_config_writes_the_pinned_checkout_as_stablemate_dir(
    tmp_path: Path, monkeypatch  # noqa: ANN001 - pytest fixture
) -> None:
    """A pinned run's effective config points at the worktree, never the live tree.

    `stablemate_dir` names "the checkout", and everything a trial derives from it
    (base-library discovery, farrier's launcher) must read the tree the round is
    measured on — copying the machine's value verbatim hands every trial the operator's
    live tree through the config, past the pin.
    """
    worktree = tmp_path / "project"
    worktree.mkdir()
    (worktree / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tracked = tmp_path / "models.toml"
    tracked.write_text("# model tables\n", encoding="utf-8")
    monkeypatch.setattr(
        sm.core_config,
        "load_config",
        lambda: {"library_dir": "/lib", "stablemate_dir": "/live/tree"},
    )
    run = SimpleNamespace(scratch=scratch, config=tracked, project=worktree)

    sm.pin_config(run)

    text = sm.effective(run).read_text(encoding="utf-8")
    assert f'stablemate_dir = "{worktree}"' in text
    assert "/live/tree" not in text
    assert 'library_dir = "/lib"' in text
