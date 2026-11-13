"""`todo reorder` refuses a list that names one queued epic twice, and writes nothing when it refuses."""

from __future__ import annotations

from pathlib import Path

import pytest
from ostler import Ostler, crud, todo
from ostler.model import load

from conftest import epics_root

pytestmark = pytest.mark.usefixtures("minting_root")


@pytest.fixture
def queue(tmp_path: Path) -> Path:
    for name in ("one", "two", "three"):
        crud.create_epic(load(tmp_path), name, name.title())
        todo.add(load(tmp_path), name)
    return tmp_path


def _bytes() -> bytes:
    return (epics_root() / "index.md").read_bytes()


def _refused(root: Path, order: list[str]):
    before = _bytes()
    res = todo.reorder(load(root), order)
    assert _bytes() == before
    assert todo.list_epics(load(root)) == ["0001-one", "0002-two", "0003-three"]
    return res


def test_the_same_name_twice_is_refused_and_named(queue: Path):
    res = _refused(queue, ["one", "one"])
    assert not res.ok
    assert res.message == "epic '0001-one' named more than once"


@pytest.mark.parametrize("order", [["two", "0002-two"], ["0002-two", "two"], ["0007-two", "0002-two"]])
def test_two_spellings_of_one_epic_are_a_repeat(queue: Path, order: list[str]):
    res = _refused(queue, order)
    assert not res.ok
    assert res.message == "epic '0002-two' named more than once"


def test_a_repeat_that_is_not_adjacent_is_refused(queue: Path):
    res = _refused(queue, ["one", "two", "one"])
    assert not res.ok
    assert res.message == "epic '0001-one' named more than once"


@pytest.mark.parametrize(
    ("order", "message"),
    [(["nope", "nope"], "not in queue: nope, nope"), (["one", "one", "nope"], "not in queue: nope")],
)
def test_an_unknown_name_is_refused_before_a_repeat(queue: Path, order: list[str], message: str):
    res = _refused(queue, order)
    assert not res.ok
    assert res.message == message


def test_two_distinct_names_go_to_the_front_in_order(queue: Path):
    assert todo.reorder(load(queue), ["two", "one"]).ok
    assert todo.list_epics(load(queue)) == ["0002-two", "0001-one", "0003-three"]


def test_one_name_moves_the_third_epic_to_the_front(queue: Path):
    assert todo.reorder(load(queue), ["three"]).ok
    assert todo.list_epics(load(queue)) == ["0003-three", "0001-one", "0002-two"]


def test_the_api_refuses_a_repeat_alike(queue: Path):
    before = _bytes()
    res = Ostler(queue).todo_reorder(["0001-one", "one"])
    assert not res.ok
    assert res.message == "epic '0001-one' named more than once"
    assert _bytes() == before
