"""The calls a book names are read from its index, which is built first when the cache is cold or stale."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from workhorse_workflows.coder.book_qa import nodes

FIXTURE = Path(__file__).resolve().parents[4] / "ostler" / "tests" / "fixtures" / "book_todo"


@pytest.fixture
def lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "lane"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__", ".ruff_cache", "node_modules", "build"))
    return root


def test_a_cold_cache_is_indexed_from_the_lane_root(lane: Path) -> None:
    held = nodes._calls_by_module(lane, ("services.api",))

    assert {"AddTodo", "FindTodos"} <= held["services.api"]
    assert nodes.book_index.stale(str(lane / "services" / "api")) is False


def test_the_index_command_keys_the_cache_by_the_folder_the_lane_resolves(lane: Path) -> None:
    folder = str(lane / "services" / "api")

    nodes._calls_by_module(lane, ("services.api",))

    assert Path(nodes.cache_path(folder)).is_file()


def test_a_fresh_cache_runs_no_command(lane: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = nodes._calls_by_module(lane, ("services.api",))

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the index was fresh")

    monkeypatch.setattr(nodes, "run_tool", refuse)

    assert nodes._calls_by_module(lane, ("services.api",)) == first


def test_a_cold_cache_runs_the_index_verb_with_the_lane_as_the_directory(lane: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[list[str], Path]] = []
    real = nodes.run_tool

    def spy(argv: list[str], cwd: Path, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append((argv, cwd))
        return real(argv, cwd=cwd, **kwargs)

    monkeypatch.setattr(nodes, "run_tool", spy)

    nodes._calls_by_module(lane, ("services.api",))

    assert [(argv[-3:], cwd) for argv, cwd in seen] == [(["ostler.book", "index", "services.api"], lane)]


def test_a_failing_index_command_raises_and_names_the_module(lane: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    monkeypatch.setattr(nodes, "run_tool", fail)

    with pytest.raises(RuntimeError, match=r"services\.api.*boom"):
        nodes._calls_by_module(lane, ("services.api",))
