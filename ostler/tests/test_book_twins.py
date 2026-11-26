"""The twins of an input: valid values that differ along one dimension of the wire type, and what the run makes of a pair."""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any, Iterator

import pytest

from ostler.book import Answer, BookError, Done, Endpoint, Environment, Field, Id, List, Model, Num, Object, Str, Enum
from ostler.book.cli import fresh
from ostler.book.http import Reply, twins
from ostler.book.inputs import Base, Tried, Twin, play, twin_classes, weigh

from book_fakes import Quiet
from book_todo import module, run_book

DAY = date(2026, 11, 4)


class Keeps(Model):
    """Reads only the day written in the value, as a model that ignores the rest of a date-time does."""

    def __init__(self, today: date, day: str = "") -> None:
        super().__init__(today)
        self.day = day

    def apply(self, request: Any) -> None:
        self.day = request.body_value["at"][:10]

    def rows(self) -> tuple[object, ...]:
        return (self.day,)

    def copy(self) -> Keeps:
        return Keeps(self.today, self.day)


class KeepsWhole(Keeps):
    def apply(self, request: Any) -> None:
        self.day = request.body_value["at"]

    def copy(self) -> KeepsWhole:
        return KeepsWhole(self.today, self.day)


class Remind(Endpoint):
    method = "POST"
    path = "/remind"
    body = Object("Remind", at=Field(Str(format="date-time")))
    answers = (Answer(200, None, "set"),)


class RemindIgnoring(Remind):
    body = Object("RemindIgnoring", at=Field(Str(format="date-time"), ignores=("offset",), why="the product keeps one day per reminder"))


class Writes(Quiet):
    def __init__(self, reading: Any) -> None:
        self.reading = reading

    def perform(self, step: Any) -> Done:
        return Done((self.reading(step.body_value["at"]),))


def written_day(at: str) -> str:
    return at[:10]


def utc_day(at: str) -> str:
    hours, minutes = int(at[11:13]), int(at[14:16])
    sign = -1 if at[19] == "-" else 1
    offset = sign * (int(at[20:22]) * 60 + int(at[23:25]))
    shifted = hours * 60 + minutes - offset
    day = date.fromisoformat(at[:10]).toordinal() + shifted // (24 * 60)
    return date.fromordinal(day).isoformat()


def _base(endpoint: type[Endpoint], model: type[Keeps]) -> Base:
    call = endpoint({"at": "2026-11-06T09:00:00+00:00"})
    return Base("test", lambda surface, make: (model(DAY), call), model(DAY), call)


def _twin(endpoint: type[Endpoint], dimension: str) -> Twin:
    return next(t for t in twin_classes(endpoint({"at": "2026-11-06T09:00:00+00:00"}), Keeps(DAY)) if t.dimension == dimension)


def _pairs(shape: Any, current: Any = None) -> dict[str, tuple[Any, Any]]:
    return {d: (a, b) for d, a, b in twins(shape, current, DAY)}


def test_a_date_time_has_a_time_of_day_and_an_offset_twin_on_the_day_it_holds():
    pairs = _pairs(Str(format="date-time"), "2026-12-24T10:00:00+00:00")
    assert pairs["time of day"] == ("2026-12-24T00:30:00+00:00", "2026-12-24T23:30:00+00:00")
    assert pairs["offset"] == ("2026-12-24T12:00:00+14:00", "2026-12-24T12:00:00-12:00")


def test_a_date_time_with_no_value_takes_a_day_after_the_models_today():
    assert _pairs(Str(format="date-time"))["offset"][0].startswith("2026-11-06T")


def test_free_text_has_a_surrounding_spaces_and_a_case_twin():
    pairs = _pairs(Str(), "Buy Milk")
    assert pairs["surrounding spaces"] == ("Buy Milk", "  Buy Milk  ")
    assert pairs["case"] == ("buy milk", "BUY MILK")


def test_text_with_no_letters_has_no_case_twin():
    assert "case" not in _pairs(Str(), "1234")


def test_text_at_its_longest_has_no_surrounding_spaces_twin():
    assert "surrounding spaces" not in _pairs(Str(max_len=8), "abcdefgh")


@pytest.mark.parametrize("shape", [Str(format="date"), Str(format="uuid"), Id(dict), Enum(("a", "b"))])
def test_a_date_an_id_an_identifier_format_and_an_enum_have_no_twins(shape):
    assert twins(shape, "2026-11-04", DAY) == []


def test_a_number_has_a_trailing_zeros_twin():
    assert twins(Num(), 2, DAY) == [("trailing zeros", 2, 2.0)]
    assert [(a, b) for _, a, b in twins(Num(text=True), "2", DAY)] == [("2", "2.0"), ("2", "2.000")]


def test_a_number_that_allows_one_decimal_has_no_three_decimal_twin():
    assert [(a, b) for _, a, b in twins(Num(text=True, places=1), "2", DAY)] == [("2", "2.0")]


def test_a_list_has_a_reversed_twin_and_a_duplicate_twin_unless_its_items_are_ids():
    assert _pairs(List(Str()), ["a", "b"]) == {"order": (["a", "b"], ["b", "a"]), "duplicate": (["a", "b"], ["a", "b", "a"])}
    ids = ["6f0f1c2e-0000-4000-8000-000000000001", "6f0f1c2e-0000-4000-8000-000000000002"]
    assert set(_pairs(List(Id(dict)), ids)) == {"order"}
    assert _pairs(List(Str()), ["a"]) == {}


def test_a_field_declares_the_dimensions_it_ignores_with_a_reason():
    with pytest.raises(BookError, match="say why"):
        Field(Str(format="date-time"), ignores=("offset",))
    with pytest.raises(BookError, match="dimensions are"):
        Field(Str(), ignores=("mood",), why="x")


def test_the_twins_of_a_call_mark_the_ones_a_field_ignores():
    kinds = {t.dimension: t.ignored for t in twin_classes(RemindIgnoring({"at": "2026-11-06T09:00:00+00:00"}), Keeps(DAY))}
    assert kinds == {"time of day": False, "offset": True}


def test_a_pair_the_model_predicts_differently_is_not_sent():
    sent: list[Any] = []

    class Spy(Writes):
        def perform(self, step: Any) -> Done:
            sent.append(step)
            return super().perform(step)

    found = weigh(Remind, _twin(Remind, "offset"), _base(Remind, KeepsWhole), Spy(written_day), lambda: KeepsWhole(DAY))
    assert found.distinguished
    assert not found.played
    assert not found.split
    assert sent == []


def test_a_pair_the_model_treats_alike_and_the_app_splits_is_underspecified():
    found = weigh(Remind, _twin(Remind, "offset"), _base(Remind, Keeps), Writes(utc_day), lambda: Keeps(DAY))
    assert found.played
    assert found.split
    assert found.twin.dimension == "offset"
    assert found.twin.name == "at"
    assert found.values == "'2026-11-06T12:00:00+14:00' and '2026-11-06T12:00:00-12:00'"


def test_the_answers_of_a_split_pair_are_named():
    found = weigh(Remind, _twin(Remind, "offset"), _base(Remind, Keeps), Writes(utc_day), lambda: Keeps(DAY))
    assert found.answers == ("ok", "ok")
    assert "2026-11-05" in found.split and "2026-11-07" in found.split


def test_a_pair_the_model_treats_alike_and_the_app_answers_alike_is_played_and_clean():
    found = weigh(Remind, _twin(Remind, "time of day"), _base(Remind, Keeps), Writes(utc_day), lambda: Keeps(DAY))
    assert found.played
    assert not found.split


def test_a_pair_on_a_dimension_the_field_ignores_is_skipped():
    found = weigh(RemindIgnoring, _twin(RemindIgnoring, "offset"), _base(RemindIgnoring, Keeps), Writes(utc_day), lambda: Keeps(DAY))
    assert found.ignored
    assert not found.played
    assert not found.split


def test_a_run_with_an_underspecified_pair_is_not_ok():
    tried = Tried()
    tried.twins.append(weigh(Remind, _twin(Remind, "offset"), _base(Remind, Keeps), Writes(utc_day), lambda: Keeps(DAY)))
    tried.twins.append(weigh(Remind, _twin(Remind, "time of day"), _base(Remind, Keeps), Writes(utc_day), lambda: Keeps(DAY)))
    assert len(tried.underspecified) == 1
    assert (tried.twins_played, tried.twins_distinguished, tried.twins_ignored) == (2, 0, 0)


class Minting(Writes):
    """A surface whose every world holds a record minted under a name of its own, and whose write adds one row."""

    def __init__(self, reading: Any) -> None:
        super().__init__(reading)
        self.worlds = 0
        self.listed: tuple[object, ...] = ()

    def arrange(self, surface: Any, make: Any) -> tuple[Model, Endpoint]:
        self.worlds += 1
        self.listed = ({"name": f"minted in world {self.worlds}"},)
        return Keeps(DAY), Remind({"at": "2026-11-06T09:00:00+00:00"})

    def rows(self) -> tuple[object, ...]:
        return self.listed

    def perform(self, step: Any) -> Done:
        reading = self.reading(step.body_value["at"])
        self.listed = (*self.listed, {"day": reading})
        return Done(self.listed)


def _minting_base(surface: Minting) -> Base:
    call = Remind({"at": "2026-11-06T09:00:00+00:00"})
    return Base("test", surface.arrange, Keeps(DAY), call)


def test_two_worlds_that_differ_in_a_record_the_call_never_touched_leave_the_pair_clean():
    surface = Minting(written_day)
    found = weigh(Remind, _twin(Remind, "offset"), _minting_base(surface), surface, lambda: Keeps(DAY))
    assert found.played
    assert found.split == ""


def test_two_worlds_that_differ_in_the_row_the_call_wrote_still_split_the_pair():
    surface = Minting(utc_day)
    found = weigh(Remind, _twin(Remind, "offset"), _minting_base(surface), surface, lambda: Keeps(DAY))
    assert found.split
    assert "2026-11-05" in found.split and "2026-11-07" in found.split


def _listing(unordered: str) -> type[Endpoint]:
    item = Object("Item", id=Field(Id(dict)), name=Field(Str()))

    class Listing(Remind):
        answers = (Answer(200, List(item, unordered=unordered), "set"),)

    return Listing


class Lists(Quiet):
    def __init__(self, endpoint: type[Endpoint], first: list[str], second: list[str]) -> None:
        self.endpoint = endpoint
        self.queue = [first, second]
        self.sent = 0

    def perform(self, step: Any) -> Done:
        names = self.queue[self.sent]
        self.sent += 1
        step.reply = Reply(200, None, self.endpoint.answers[0])
        return Done((), tuple({"id": f"world-{self.sent}-{n}", "name": n} for n in names))


def _weigh_lists(unordered: str, first: list[str], second: list[str]) -> Any:
    endpoint = _listing(unordered)
    return weigh(endpoint, _twin(endpoint, "offset"), _base(endpoint, Keeps), Lists(endpoint, first, second), lambda: Keeps(DAY))


def test_two_answers_holding_the_same_items_of_an_unordered_list_in_another_order_are_alike():
    found = _weigh_lists("the product sets no order", ["a", "b", "c"], ["c", "a", "b"])
    assert found.played
    assert found.split == ""


def test_two_answers_differing_in_an_item_of_an_unordered_list_are_told_apart():
    found = _weigh_lists("the product sets no order", ["a", "b", "c"], ["c", "a", "d"])
    assert found.split


def test_a_list_not_declared_unordered_is_compared_by_position():
    found = _weigh_lists("", ["a", "b", "c"], ["c", "a", "b"])
    assert found.split


@pytest.fixture
def todo_server() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


@pytest.fixture
def utc_server() -> Iterator:
    server = module("app").TodoServer(bug="remind_utc").start()
    yield server
    server.stop()


def _play_fixture(server: Any) -> Tried:
    service = module("services.api.service").service
    surface = service.surface(Environment("local", {"api": server.url}))
    return play(service, surface, lambda: fresh(service, surface), only=frozenset({"AddTodo"}))


def test_the_todo_book_plays_its_twins_and_finds_nothing_against_an_app_that_reads_the_written_day(todo_server, tmp_path):
    done = run_book(["run", "services.api", "--no-stack", "--out", str(tmp_path)], todo_server.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Underspecified" not in done.stdout
    assert "twins: 14 pairs played, 0 skipped because the model distinguished them, 0 underspecified" in done.stdout


def test_the_todo_book_reports_a_reminder_the_app_reads_in_utc_and_the_model_reads_as_written(utc_server, tmp_path):
    done = run_book(["run", "services.api", "--no-stack", "--out", str(tmp_path)], utc_server.port)
    assert done.returncode == 1, done.stdout + done.stderr
    found = [line for line in done.stdout.partition("Stated and never played")[0].splitlines() if line.startswith("- ")]
    assert len(found) == 2
    assert all("remind_at offset" in line for line in found)
    assert {line.split()[1] for line in found} == {"AddTodo", "UpdateTodo"}
    assert "twins: 14 pairs played, 0 skipped because the model distinguished them, 2 underspecified" in done.stdout
    assert "## Underspecified" in (tmp_path / "api.md").read_text()


def test_the_split_names_the_field_the_dimension_and_the_two_days(utc_server):
    tried = _play_fixture(utc_server)
    [only] = tried.underspecified
    assert (only.twin.name, only.twin.dimension) == ("remind_at", "offset")
    assert "remind_day" in only.split


def test_the_todo_book_skips_the_pair_where_the_field_declares_the_offset_ignored(utc_server, monkeypatch):
    body = module("services.api.endpoints.shapes").TODO_INPUT
    declared = dataclasses.replace(body.fields["remind_at"], ignores=("offset",), why="the product keeps the day as written")
    monkeypatch.setitem(body.fields, "remind_at", declared)
    tried = _play_fixture(utc_server)
    assert tried.underspecified == []
    assert tried.twins_ignored == 1


def test_both_values_of_a_pair_take_a_world_arranged_anew_after_a_clean_class(todo_server):
    service = module("services.api.service").service
    surface = service.surface(Environment("local", {"api": todo_server.url}))
    arranged = []

    def counted() -> Model:
        arranged.append(1)
        return fresh(service, surface)

    tried = play(service, surface, counted, only=frozenset({"AddTodo"}))
    assert tried.twins_played
    assert tried.sent[-1].clean
    anew = sum(1 for before, s in zip([None, *tried.sent], tried.sent) if before is None or not before.clean)
    assert len(arranged) == anew + 2 * tried.twins_played
