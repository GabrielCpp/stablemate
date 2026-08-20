"""The frozen-app trial's setup ordering: what the before-commit has to already contain.

One property, and it is the one that cost every trial of the first scoring round a
`repair-qa-context` lap: the QA lane mints its obligations from `HEAD..WORKTREE`, so
anything created in the trial tree *after* the before-commit is indistinguishable from the
story's implementation. `farrier install` creates half a dozen such files. It therefore has
to run inside `materialize`, before the commit — and a test is the only thing that keeps it
there, because moving it back out breaks nothing that fails loudly.
"""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml

BENCHMARKS = Path(__file__).parents[1]
APP = BENCHMARKS / "apps" / "policy-desk"


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does.

    Task modules are loose files that import their siblings by bare name, so a loader —
    here, the test — has to put their directory on the path the way `python tasks/x.py`
    would, and take it off again.
    """
    saved = sys.path[:]
    sys.path.insert(0, str(BENCHMARKS / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load_frozenapp() -> ModuleType:
    path = BENCHMARKS / "tasks" / "_frozenapp.py"
    spec = importlib.util.spec_from_file_location("_frozenapp", path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        sys.modules["_frozenapp"] = module
        spec.loader.exec_module(module)
    return module


frozenapp = _load_frozenapp()


def manifest(story: str) -> set[str]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {*(data.get("changed") or []), *(data.get("added") or [])}


def dirty(repo: Path) -> set[str]:
    lines = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return {line[3:] for line in lines}


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_the_install_layer_is_committed_with_the_before_tree(tmp_path: Path) -> None:
    generated = ".claude/skills/pretend/scripts/run.sh"

    def install(repo: Path) -> None:
        target = repo / generated
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\n", encoding="utf-8")

    dest = frozenapp.materialize(APP, "create-policy", tmp_path / "policy-desk", install)

    # The generated file exists and is *not* part of the diff the QA lane will be asked to
    # own — which is the whole property. Were `install` run after the commit, it would be.
    assert (dest / generated).is_file()
    assert dirty(dest) == manifest("create-policy")


@pytest.mark.skipif(not APP.is_dir(), reason="the policy-desk fixture is not in this tree")
def test_materialize_without_an_installer_is_unchanged(tmp_path: Path) -> None:
    dest = frozenapp.materialize(APP, "create-policy", tmp_path / "policy-desk")
    assert dirty(dest) == manifest("create-policy")
