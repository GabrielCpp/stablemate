"""A task's named lock: held for the whole round, exclusive, and released when a step raises."""

from __future__ import annotations

import fcntl
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from paddock.loader import Benchmark
from paddock.locks import hold_lock
from paddock.runner import execute

MakeBenchmark = Callable[..., Benchmark]

LOCKED_TASKS = '''"""A locked task whose step raises."""
from paddock import step, task

task(name="smoke", lock="stack")

@step()
def boom(run):
    raise RuntimeError("step failed")
'''


@pytest.fixture
def lock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache" / "paddock" / "locks"


def test_a_second_holder_of_a_lock_blocks_until_the_first_lets_go(lock_home: Path) -> None:
    acquired = threading.Event()

    def second() -> None:
        with hold_lock("stack"):
            acquired.set()

    with hold_lock("stack") as path:
        assert path == lock_home / "stack.lock"
        assert os.environ["PADDOCK_LOCK_FILE"] == str(path)
        waiter = threading.Thread(target=second, daemon=True)
        waiter.start()
        assert not acquired.wait(0.5)
    assert acquired.wait(5)
    waiter.join(5)
    assert "PADDOCK_LOCK_FILE" not in os.environ


def test_a_locked_task_releases_its_lock_when_a_step_raises(
    make_benchmark: MakeBenchmark, root: Path, repo: Path, lock_home: Path
) -> None:
    benchmark = make_benchmark(LOCKED_TASKS)
    result = execute(benchmark, benchmark.task("smoke"), root=root, checkout=repo)
    assert not result.ok
    with (lock_home / "stack.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
