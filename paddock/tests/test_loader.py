"""Task modules are Python, and a malformed one raises with a line number."""

from __future__ import annotations

from pathlib import Path

import pytest

from paddock import loader
from paddock.registry import TaskError

GOOD = '''
"""A task that does nothing, twice."""
from paddock import Score, step, task

task(name="demo", seed="acme", config="configs/test.toml")

@step()
def first(run):
    """The first thing."""

@step(name="renamed")
def second(run):
    pass

def score(run):
    return Score(headline="fine")
'''


def write(data_dir: Path, name: str, body: str) -> Path:
    path = data_dir / "tasks" / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_module_declares_a_task_with_its_steps_in_order(data_dir: Path) -> None:
    task = loader.load_path(write(data_dir, "demo", GOOD))
    assert task.name == "demo"
    assert [item.name for item in task.steps] == ["first", "renamed"]
    assert task.steps[0].doc == "The first thing."
    assert task.score is not None
    assert task.describe().endswith("2 steps  scored")


def test_a_second_task_call_is_an_error(data_dir: Path) -> None:
    path = write(data_dir, "twice", GOOD + '\ntask(name="again", seed="a", config="b")\n')
    with pytest.raises(TaskError, match="already called"):
        loader.load_path(path)


def test_a_step_declared_before_the_task_is_an_error(data_dir: Path) -> None:
    path = write(
        data_dir,
        "early",
        "from paddock import step\n\n@step()\ndef nope(run):\n    pass\n",
    )
    with pytest.raises(TaskError, match="before task"):
        loader.load_path(path)


def test_a_module_with_no_steps_is_an_error(data_dir: Path) -> None:
    path = write(
        data_dir,
        "bare",
        'from paddock import task\n\ntask(name="bare", seed="a", config="b")\n',
    )
    with pytest.raises(TaskError, match="no steps"):
        loader.load_path(path)


def test_a_duplicate_step_name_is_an_error(data_dir: Path) -> None:
    path = write(
        data_dir,
        "dupe",
        GOOD + '\n@step(name="renamed")\ndef third(run):\n    pass\n',
    )
    with pytest.raises(TaskError, match="declared twice"):
        loader.load_path(path)


def test_modules_do_not_leak_declarations_into_each_other(data_dir: Path) -> None:
    # The registry is module-scoped state; loading two tasks in one process must not
    # append the first module's steps to the second's.
    write(data_dir, "demo", GOOD)
    write(data_dir, "other", GOOD.replace('name="demo"', 'name="other"'))
    tasks = loader.load_all(data_dir)
    assert [task.name for task in tasks] == ["demo", "other"]
    assert all(len(task.steps) == 2 for task in tasks)


def test_two_modules_claiming_one_name_is_an_error(data_dir: Path) -> None:
    write(data_dir, "demo", GOOD)
    write(data_dir, "clone", GOOD)
    with pytest.raises(TaskError, match="declared twice"):
        loader.load_all(data_dir)


def test_an_unknown_task_names_the_ones_that_exist(data_dir: Path) -> None:
    write(data_dir, "demo", GOOD)
    with pytest.raises(TaskError, match="known: demo"):
        loader.load_named(data_dir, "missing")
