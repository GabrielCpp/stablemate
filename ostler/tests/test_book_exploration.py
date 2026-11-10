"""Exploration on the model alone: the signature, the dedupe, the stop rule and the cells."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, cast

import pytest

from ostler.book import Action, Arrange, Axes, Fixture, Model, Rule, Service
from ostler.book.check import check
from ostler.book.model import Refused
from ostler.book.exploration import BASELINE, REFUSED, Node, calls, cells_at, code, effect, outside_moves, seed, signature, walk

from book_fakes import Quiet, no_stack
from book_todo import module

DAY = date(2026, 11, 4)

api = module("services.api.service").service
endpoints = module("services.api.endpoints")
fixtures = module("services.api.fixtures")
AddTodo, FindTodos, SetStore = endpoints.AddTodo, endpoints.FindTodos, endpoints.SetStore
Switch, todo = fixtures.Switch, fixtures.todo


class Heap(Model):
    """A model that keeps a count of identical things, at most three."""

    def __init__(self, today: date, n: int = 0):
        super().__init__(today)
        self.n = n

    def apply(self, request: object) -> None:
        if self.n >= 3:
            raise Refused(Rule("full", lambda a, s, by: True))
        self.n += 1

    def copy(self) -> Heap:
        return Heap(self.today, self.n)


def heap_service(state_of: Any = lambda m, e: "x") -> Service[Heap]:
    axes = Axes[Heap]("heap", DAY, (), {}, lambda m: str(m.n), state_of=state_of, entities=lambda m: ["x"] * m.n)
    return Service[Heap](name="heap", new_model=Heap, surface=lambda environment: Quiet(), journeys=(),
                         stack=no_stack, matrices=(axes,))


@dataclass
class Parcel(Fixture):
    slot: int = 0

    @classmethod
    def examples(cls, state: Any, by: Any) -> Iterable[Parcel]:
        return [cls(slot=n) for n in range(2) if state.n <= n]


@dataclass
class Bare(Fixture):
    slot: int = 0


class Take(Action):
    accept = Parcel


class TakeBare(Action):
    accept = Bare


class Arrives(Arrange[Parcel]):
    does = "a parcel arrives"
    carries = Take


class ArrivesBare(Arrange[Bare]):
    does = "a bare parcel arrives"
    carries = TakeBare


def outside_service(*events: type[Arrange[Any]]) -> Service[Heap]:
    service = heap_service()
    service.outside = events
    return service


def test_a_count_is_none_one_or_many():
    service = heap_service()
    told = [signature(service, Heap(DAY, n)) for n in range(4)]
    assert len(set(told)) == 3
    assert told[2] == told[3]


def test_the_day_does_not_tell_two_states_apart():
    service = heap_service()
    assert signature(service, Heap(DAY, 1)) == signature(service, Heap(DAY + timedelta(days=1), 1))


def test_a_chore_is_told_by_its_status():
    models = [api.new_model(DAY) for _ in range(4)]
    for count, model in enumerate(models):
        for title in "ABC"[:count]:
            model.apply(AddTodo(todo(title)))
    told = [signature(api, m) for m in models]
    assert len(set(told)) == 3
    assert told[2] == told[3]


def test_a_state_met_twice_is_kept_once(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.exploration.calls", lambda service, model: ["add"])
    walked = walk(heap_service(), Heap(DAY), 4)
    assert len({n.signature for n in walked.nodes}) == len(walked.nodes)


def test_a_depth_with_no_new_signature_ends_the_walk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.exploration.calls", lambda service, model: ["add"])
    walked = walk(heap_service(), Heap(DAY), 8)
    assert walked.per_depth == [1, 1, 1]
    assert walked.reached == 2
    assert walked.stopped == "depth 3 added no new signature"


def test_the_bound_caps_the_walk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ostler.book.exploration.calls", lambda service, model: ["add"])
    walked = walk(heap_service(), Heap(DAY), 1)
    assert walked.reached == 1
    assert walked.stopped == "the depth bound 1"


def test_a_path_replays_on_another_model():
    walked = walk(api, api.new_model(DAY), 2)
    for node in walked.nodes:
        replayed = api.new_model(DAY)
        for position in node.path:
            replayed.apply(calls(api, replayed)[position])
        assert signature(api, replayed) == node.signature


def test_a_cell_is_keyed_once_per_state_endpoint_actor_and_class():
    walked, cells = seed(api, api.new_model(DAY), 2)
    keys = [c.key for c in cells]
    assert len(keys) == len(set(keys))
    assert any(c.label == BASELINE for c in cells)
    assert all(c.actor for c in cells)


def test_classes_play_once_per_endpoint_and_actor_baselines_at_every_state():
    walked, cells = seed(api, api.new_model(DAY), 3)
    classes = [c for c in cells if c.label != BASELINE and not c.label.startswith(REFUSED)]
    assert classes
    triples = [(c.endpoint, c.actor, c.label) for c in classes]
    assert len(triples) == len(set(triples))
    first: dict[tuple[str, str], str] = {}
    for node in walked.nodes:
        for c in cells_at(api, node):
            if c.label == BASELINE:
                first.setdefault((c.endpoint, c.actor), node.signature)
    for c in classes:
        assert c.node.signature == first[(c.endpoint, c.actor)]
    baselines = [c for c in cells if c.label == BASELINE]
    assert len(baselines) > len({(c.endpoint, c.actor) for c in baselines})


def test_a_refused_baseline_has_a_refusal_cell_and_no_baseline():
    model = api.new_model(DAY)
    model.apply(SetStore(Switch(down=True)))
    found = cells_at(api, Node(signature(api, model), 0, (), model))
    adds = [c for c in found if c.endpoint == "AddTodo"]
    assert adds
    assert all(c.label.startswith(REFUSED) for c in adds)
    assert any(c.endpoint == "SetStore" and c.label == BASELINE for c in found)


def test_a_read_changes_nothing_and_an_add_writes():
    model = api.new_model(DAY)
    assert effect(model, AddTodo(todo("A")))[1]
    assert not effect(model, FindTodos())[1]


def test_an_event_is_aimed_at_each_example_the_state_gives():
    service = outside_service(Arrives)
    assert [cast(Parcel, m.of).slot for m in outside_moves(service, Heap(DAY, 0))] == [0, 1]
    assert [cast(Parcel, m.of).slot for m in outside_moves(service, Heap(DAY, 1))] == [1]
    assert outside_moves(service, Heap(DAY, 2)) == []


def test_an_event_has_no_caller_and_follows_the_calls(monkeypatch: pytest.MonkeyPatch):
    service = outside_service(Arrives)
    monkeypatch.setattr("ostler.book.exploration.own_calls", lambda service, model: ["add"])
    offered = calls(service, Heap(DAY))
    assert offered[0] == "add"
    assert all(isinstance(m, Arrives) and m.by is None for m in offered[1:])


def test_the_walk_takes_an_event_and_its_path_replays(monkeypatch: pytest.MonkeyPatch):
    service = outside_service(Arrives)
    monkeypatch.setattr("ostler.book.exploration.own_calls", lambda service, model: [])
    walked = walk(service, Heap(DAY), 4)
    assert len(walked.nodes) > 1
    for node in walked.nodes:
        replayed = Heap(DAY)
        for position in node.path:
            replayed.apply(calls(service, replayed)[position])
        assert signature(service, replayed) == node.signature


def test_an_event_is_not_a_cell(monkeypatch: pytest.MonkeyPatch):
    service = outside_service(Arrives)
    monkeypatch.setattr("ostler.book.exploration.own_calls", lambda service, model: [])
    assert cells_at(service, Node("x", 0, (), Heap(DAY))) == []


def test_a_replay_names_the_event():
    assert "Arrives" in code(Arrives(Parcel(slot=1)))


def test_check_names_an_event_whose_fixture_gives_no_examples():
    found = [str(f) for f in check(outside_service(Arrives, ArrivesBare), __name__)]
    assert any("outside ArrivesBare" in f for f in found), found
    assert not any("outside Arrives:" in f for f in found), found


def test_check_names_a_matrix_without_state_of():
    found = [str(f) for f in check(heap_service(None), __name__)]
    assert any("declares no state_of" in f for f in found), found
