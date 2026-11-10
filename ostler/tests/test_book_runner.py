"""How a step is judged on the model and the surface, and how an outside event is waited for."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from ostler.book import Answer, Arrange, Endpoint, OffShape, Refusal
from ostler.book.http import Identities
from ostler.book.runner import PATIENCE, Landings, landed, perform, spoken

from book_fakes import Counter as Tally
from book_fakes import Quiet

DAY = date(2026, 11, 4)


class Counter(Tally):
    def counts(self, request: object) -> bool:
        return isinstance(request, Bump)


class Bump(Arrange[int]):
    does = "a bump arrives"


class Peek(Endpoint):
    path = "/peek"
    answers = (Answer(200, None, "seen"),)


class Late(Quiet):
    """A surface whose rows change on a given read, and which raises off its shape on others."""

    def __init__(self, lands_on: int, off_shape_on: tuple[int, ...] = ()) -> None:
        self.reads = 0
        self.lands_on = lands_on
        self.off_shape_on = off_shape_on

    def rows(self) -> tuple[object, ...]:
        self.reads += 1
        if self.reads in self.off_shape_on:
            raise OffShape(Peek, 200, ["body: expected a list"])
        return (1,) if self.reads >= self.lands_on else (0,)


@pytest.fixture(autouse=True)
def landings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Landings, "longest", 0)
    monkeypatch.setattr(Landings, "missed", False)


def test_after_an_arrange_the_watch_is_read_again_until_it_shows_the_model():
    surface = Late(lands_on=3)
    step = Bump()
    result = perform(step, step, Counter(DAY), surface)
    assert result.ok
    assert surface.reads == 3
    assert Landings.longest == 3
    assert not Landings.missed


def test_a_reading_off_its_shape_on_the_way_is_tolerated():
    surface = Late(lands_on=3, off_shape_on=(1, 2))
    rows, reads = landed(surface, (1,))
    assert rows == (1,)
    assert reads == 3


def test_a_reading_off_its_shape_on_the_last_read_is_raised(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.runner.RETAKES", 2)
    with pytest.raises(OffShape):
        landed(Late(lands_on=9, off_shape_on=(1, 2)), (1,))
    assert Landings.missed


def test_an_event_that_never_lands_is_judged_on_the_last_reading(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.runner.RETAKES", 4)
    surface = Late(lands_on=99)
    rows, reads = landed(surface, (1,))
    assert rows == (0,)
    assert reads == 4
    assert surface.reads == 4
    assert Landings.missed


def test_after_one_miss_the_bound_drops(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.runner.RETAKES", 1000)
    assert Landings.bound() == 1000
    monkeypatch.setattr(Landings, "missed", True)
    assert Landings.bound() == PATIENCE
    monkeypatch.setattr(Landings, "longest", 40)
    assert Landings.bound() == 120


def test_a_step_that_lands_after_a_miss_is_still_read_within_the_lower_bound():
    Landings.missed = True
    surface = Late(lands_on=7)
    assert landed(surface, (1,)) == ((1,), 7)



def test_a_model_refusal_that_quotes_an_app_id_is_read_under_the_model_id() -> None:
    class Asset:
        pass

    class Desk(Quiet):
        def __init__(self) -> None:
            self.client = SimpleNamespace(ids=Identities())

    surface = Desk()
    surface.client.ids.learn(Asset, "asset-1", "AS-15")
    told = spoken(surface, Refusal("user AS-15 not found", 404))
    assert told == Refusal("user asset-1 not found", 404)
    assert spoken(surface, Refusal("user AS-150 not found", 404)) == Refusal("user AS-150 not found", 404)
    assert spoken(Quiet(), Refusal("user AS-15 not found", 404)) == Refusal("user AS-15 not found", 404)
