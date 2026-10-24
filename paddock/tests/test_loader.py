"""A benchmark folder is loaded from `gold/`, and a malformed tasks module raises with a line number."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from paddock import loader
from paddock.loader import Benchmark
from paddock.registry import TaskError

from smoke import SMOKE_TASKS

MakeBenchmark = Callable[..., Benchmark]

TWO_STEPS = '''
"""A task that does nothing, twice."""
from paddock import Score, step, task

task(name="demo", config={"profiles": {"claude": {"model": "x"}}})

@step()
def first(run):
    """The first thing."""

@step(name="renamed")
def second(run):
    pass

def score(run):
    return Score(headline="fine")
'''


def write(directory: Path, body: str) -> Path:
    path = directory / "tasks.py"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_a_module_declares_a_task_with_its_steps_in_order(tmp_path: Path) -> None:
    task = loader.load_path(write(tmp_path / "demo", TWO_STEPS))
    assert task.name == "demo"
    assert [item.name for item in task.steps] == ["first", "renamed"]
    assert task.steps[0].doc == "The first thing."
    assert task.config == {"profiles": {"claude": {"model": "x"}}}
    assert task.score is not None
    assert task.describe().endswith("2 steps  scored")


def test_a_task_without_a_config_overrides_nothing(tmp_path: Path) -> None:
    task = loader.load_path(write(tmp_path / "demo", TWO_STEPS.replace(', config={"profiles": {"claude": {"model": "x"}}}', "")))
    assert task.config == {}


def test_a_seed_is_no_longer_part_of_a_task(tmp_path: Path) -> None:
    path = write(tmp_path / "demo", TWO_STEPS.replace('task(name="demo"', 'task(name="demo", seed="acme"'))
    with pytest.raises(TypeError, match="seed"):
        loader.load_path(path)


def test_a_second_task_call_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "twice", TWO_STEPS + '\ntask(name="again")\n')
    with pytest.raises(TaskError, match="already called"):
        loader.load_path(path)


def test_a_step_declared_before_the_task_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "early", "from paddock import step\n\n@step()\ndef nope(run):\n    pass\n")
    with pytest.raises(TaskError, match="before task"):
        loader.load_path(path)


def test_a_module_with_no_steps_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "bare", 'from paddock import task\n\ntask(name="bare")\n')
    with pytest.raises(TaskError, match="no steps"):
        loader.load_path(path)


def test_a_duplicate_step_name_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "dupe", TWO_STEPS + '\n@step(name="renamed")\ndef third(run):\n    pass\n')
    with pytest.raises(TaskError, match="declared twice"):
        loader.load_path(path)


def test_loading_puts_nothing_on_sys_path(tmp_path: Path) -> None:
    before = list(sys.path)
    loader.load_path(write(tmp_path / "demo", TWO_STEPS))
    assert sys.path == before


def test_a_benchmark_is_its_folder_and_its_task(make_benchmark: MakeBenchmark, root: Path) -> None:
    benchmark = make_benchmark()
    assert benchmark.name == "smoke"
    assert benchmark.task.name == "smoke"
    assert benchmark.home_config == root / "gold" / "smoke" / "home-config.toml"
    assert benchmark.data == root / "gold" / "smoke" / "data"


def test_every_benchmark_under_gold_is_listed(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    make_benchmark(SMOKE_TASKS.replace('name="smoke"', 'name="other"'), name="second")
    assert loader.benchmark_names(root) == ["second", "smoke"]
    assert [item.task.name for item in loader.load_all(root)] == ["other", "smoke"]


def test_an_empty_root_lists_nothing(root: Path) -> None:
    assert loader.load_all(root) == []


def test_an_unknown_benchmark_names_the_ones_that_exist(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    with pytest.raises(TaskError, match="Known: smoke"):
        loader.load_benchmark(root, "missing")


def test_an_unknown_task_names_the_one_the_benchmark_declares(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    with pytest.raises(TaskError, match="Known: smoke"):
        loader.load_task(root, "smoke", "missing")


def test_a_benchmark_missing_a_part_names_it(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    (root / "gold" / "smoke" / "home-config.toml").unlink()
    with pytest.raises(TaskError, match="lacks home-config.toml"):
        loader.load_benchmark(root, "smoke")
