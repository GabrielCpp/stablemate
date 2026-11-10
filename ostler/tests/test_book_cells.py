"""The state table played on a surface: which cells share an arrangement."""

from __future__ import annotations

from datetime import date

from ostler.book import Axes, Done, Scene
from ostler.book.cells import play

from book_fakes import Counter as Tally
from book_fakes import Quiet

DAY = date(2026, 11, 4)


class Counter(Tally):
    def counts(self, request: object) -> bool:
        return request == "bump"


class Mirror(Quiet):
    def __init__(self) -> None:
        self.n = 0

    def perform(self, step: object) -> Done:
        if step == "bump":
            self.n += 1
        return Done((self.n,))

    def rows(self) -> tuple[object, ...]:
        return (self.n,)


class Fresh:
    def __init__(self, surface: Mirror) -> None:
        self.made = 0
        self.surface = surface

    def __call__(self) -> Counter:
        self.made += 1
        self.surface.n = 0
        return Counter(DAY)


def _axes(*actions: str) -> Axes[Counter]:
    scene = Scene("empty", "nothing was done", lambda today: ())
    return Axes[Counter]("counter", DAY, (scene,), {name: (lambda model, name=name: name.split()[0]) for name in actions},
                         lambda model: str(model.n))


def test_two_read_cells_of_one_scene_share_an_arrangement():
    surface = Mirror()
    fresh = Fresh(surface)
    played = play((_axes("read one", "read two"),), surface, fresh)
    assert [c.ok for c in played.cells] == [True, True]
    assert played.arrangements == 1
    assert fresh.made == 1


def test_a_cell_that_changes_the_model_does_not_hand_it_on():
    surface = Mirror()
    fresh = Fresh(surface)
    played = play((_axes("bump", "read"),), surface, fresh)
    assert [c.ok for c in played.cells] == [True, True]
    assert played.arrangements == 2
    assert fresh.made == 2


def test_a_read_after_a_read_keeps_the_arrangement_a_write_after_it_ends():
    surface = Mirror()
    fresh = Fresh(surface)
    played = play((_axes("read one", "read two", "bump", "read three"),), surface, fresh)
    assert played.arrangements == 2
    assert fresh.made == 2
