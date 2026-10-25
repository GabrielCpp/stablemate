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
from paddock import Score, score, step, task

task(name="demo", config={"profiles": {"claude": {"model": "x"}}})

@step()
def first(run):
    """The first thing."""

@step(name="renamed")
def second(run):
    pass

@score()
def grade(run):
    return Score(headline="fine")
'''


def write(directory: Path, body: str) -> Path:
    path = directory / "tasks.py"
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_a_module_declares_a_task_with_its_steps_in_order(tmp_path: Path) -> None:
    (task,) = loader.load_path(write(tmp_path / "demo", TWO_STEPS))
    assert task.name == "demo"
    assert [item.name for item in task.steps] == ["first", "renamed"]
    assert task.steps[0].doc == "The first thing."
    assert task.config == {"profiles": {"claude": {"model": "x"}}}
    assert task.score is not None
    assert task.describe().endswith("2 steps  scored")


def test_a_task_without_a_config_overrides_nothing(tmp_path: Path) -> None:
    (task,) = loader.load_path(write(tmp_path / "demo", TWO_STEPS.replace(', config={"profiles": {"claude": {"model": "x"}}}', "")))
    assert task.config == {}


def test_a_seed_is_no_longer_part_of_a_task(tmp_path: Path) -> None:
    path = write(tmp_path / "demo", TWO_STEPS.replace('task(name="demo"', 'task(name="demo", seed="acme"'))
    with pytest.raises(TypeError, match="seed"):
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
    assert [item.name for item in benchmark.tasks] == ["smoke"]
    assert benchmark.home_config == root / "gold" / "smoke" / "home-config.toml"
    assert benchmark.data == root / "gold" / "smoke" / "data"


def test_every_benchmark_under_gold_is_listed(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    make_benchmark(SMOKE_TASKS.replace('name="smoke"', 'name="other"'), name="second")
    assert loader.benchmark_names(root) == ["second", "smoke"]
    assert [item.tasks[0].name for item in loader.load_all(root)] == ["other", "smoke"]


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


def test_the_data_repos_are_each_data_repo_or_each_repo_in_a_folder_of_them(
    make_benchmark: MakeBenchmark, root: Path
) -> None:
    make_benchmark()
    folder = root / "gold" / "multi" / "data"
    for repo in ("web-app", "api-service"):
        (folder / repo / ".git").mkdir(parents=True)
    (folder / ".hidden").mkdir()
    assert loader.data_repos(root) == [
        folder / "api-service", folder / "web-app", root / "gold" / "smoke" / "data"]


def test_a_benchmark_missing_a_part_names_it(make_benchmark: MakeBenchmark, root: Path) -> None:
    make_benchmark()
    (root / "gold" / "smoke" / "home-config.toml").unlink()
    with pytest.raises(TaskError, match="lacks home-config.toml"):
        loader.load_benchmark(root, "smoke")


TWO_TASKS = '''
"""Two tasks in one module."""
from paddock import Score, score, step, task

task(name="first", inputs={"n": 1})

@step()
def touch(run):
    pass

@score()
def first_score(run):
    return Score(headline="first")

task(name="second")

@step()
def touch_again(run):
    pass

@step()
def and_again(run):
    pass

@score()
def second_score(run):
    return Score(headline="second")
'''


def test_a_module_declares_several_tasks_each_with_its_own_steps_and_score(tmp_path: Path) -> None:
    first, second = loader.load_path(write(tmp_path / "demo", TWO_TASKS))
    assert (first.name, second.name) == ("first", "second")
    assert [item.name for item in first.steps] == ["touch"]
    assert [item.name for item in second.steps] == ["touch_again", "and_again"]
    assert first.inputs == {"n": 1}
    assert second.inputs == {}
    assert first.score is not None
    assert second.score is not None
    assert first.score is not second.score


def test_a_task_without_a_score_decorator_is_unscored(tmp_path: Path) -> None:
    body = TWO_TASKS.replace("@score()\ndef second_score", "def second_score")
    first, second = loader.load_path(write(tmp_path / "demo", body))
    assert first.score is not None
    assert second.score is None
    assert second.describe().endswith("2 steps  unscored")


def test_a_module_level_score_function_is_not_a_score(tmp_path: Path) -> None:
    body = (
        "from paddock import Score, step, task\n\n"
        'task(name="plain")\n\n'
        "@step()\ndef go(run):\n    pass\n\n"
        'def score(run):\n    return Score(headline="ignored")\n'
    )
    (plain,) = loader.load_path(write(tmp_path / "demo", body))
    assert plain.score is None


def test_a_repeated_task_name_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "twice", TWO_STEPS + '\ntask(name="demo")\n')
    with pytest.raises(TaskError, match="declared twice"):
        loader.load_path(path)


def test_a_second_score_on_one_task_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "twice", TWO_STEPS + '\n@score()\ndef another(run):\n    return Score(headline="x")\n')
    with pytest.raises(TaskError, match="already has a score"):
        loader.load_path(path)


def test_a_score_declared_before_the_task_is_an_error(tmp_path: Path) -> None:
    path = write(tmp_path / "early", "from paddock import score\n\n@score()\ndef nope(run):\n    pass\n")
    with pytest.raises(TaskError, match="before task"):
        loader.load_path(path)


def test_a_task_without_steps_is_refused_even_when_a_later_one_has_them(tmp_path: Path) -> None:
    path = write(tmp_path / "bare", 'from paddock import step, task\n\ntask(name="bare")\ntask(name="full")\n\n@step()\ndef go(run):\n    pass\n')
    with pytest.raises(TaskError, match="'bare' declares no steps"):
        loader.load_path(path)


def test_a_benchmark_finds_its_task_by_name(make_benchmark: MakeBenchmark) -> None:
    benchmark = make_benchmark(TWO_TASKS)
    assert benchmark.task("second").name == "second"
    with pytest.raises(TaskError, match="Known: first, second"):
        benchmark.task("third")


def test_a_sibling_helper_imports_while_loading_and_sys_path_is_restored(tmp_path: Path) -> None:
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "helper.py").write_text("VALUE = 'from the helper'\n", encoding="utf-8")
    body = TWO_TASKS.replace("from paddock import", "import helper\nfrom paddock import", 1).replace(
        'task(name="second")', 'task(name="second", inputs={"v": helper.VALUE})'
    )
    before = list(sys.path)
    _, second = loader.load_path(write(directory, body))
    assert second.inputs == {"v": "from the helper"}
    assert sys.path == before
    assert "helper" not in sys.modules


def test_sys_path_is_restored_when_the_module_fails_to_import(tmp_path: Path) -> None:
    before = list(sys.path)
    with pytest.raises(RuntimeError, match="boom"):
        loader.load_path(write(tmp_path / "demo", 'raise RuntimeError("boom")\n'))
    assert sys.path == before
