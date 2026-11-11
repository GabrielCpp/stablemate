"""A refusal that keeps what the call did before it refused: a batch the service stops halfway."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any, ClassVar

from ostler.book import Action, Actor, Collection, Create, Defect, Done, Refusal, Rule, State, Transaction, Unique, Update
from ostler.book.outcome import Flawed

DAY = date(2026, 11, 10)


@dataclass(frozen=True)
class Order:
    id: str
    supplier: str
    sent: bool = False


@dataclass(frozen=True)
class Batch:
    ids: tuple[str, ...]


class Orders(State):
    orders = Collection(Order, Unique("id"))

    def rows(self) -> tuple[object, ...]:
        return tuple(self.orders)


def _deliverable(s: Orders, ids: tuple[str, ...]) -> tuple[str, ...]:
    """The orders of the batch sent before the first one whose supplier refuses."""
    kept: list[str] = []
    for key in ids:
        if s.orders[key].supplier == "refuses":
            break
        kept.append(key)
    return tuple(kept)


def _mark(s: Orders, ids: tuple[str, ...]) -> Transaction:
    return Transaction(*(Update(Orders.orders, key, replace(s.orders[key], sent=True)) for key in ids))


def _refused_on(s: Orders, ids: tuple[str, ...]) -> bool:
    return len(_deliverable(s, ids)) < len(ids)


delivery_refused = Rule[Batch, Orders](
    "a supplier refused the delivery",
    lambda a, s, by: _refused_on(s, a.ids),
    status=424,
    does=lambda a, s, by: _mark(s, _deliverable(s, a.ids)),
)

silent_refusal = Rule[Batch, Orders]("a supplier refused the delivery", lambda a, s, by: _refused_on(s, a.ids), status=424)


class Send(Action[Batch, Orders]):
    accept = Batch
    rules = (delivery_refused,)

    @staticmethod
    def reduce(a: Batch, s: Orders, by: Actor | None) -> Transaction:
        return _mark(s, a.ids)


class SendSilently(Send):
    rules = (silent_refusal,)


@dataclass(frozen=True)
class SendOrders:
    batch: Batch
    by: Any = None
    carries: ClassVar[type[Action[Any, Any]]] = Send

    def input(self) -> Batch:
        return self.batch


@dataclass(frozen=True)
class SendOrdersSilently(SendOrders):
    carries: ClassVar[type[Action[Any, Any]]] = SendSilently


def _orders(*suppliers: str) -> Orders:
    state = Orders(DAY)
    for n, supplier in enumerate(suppliers):
        Create(Orders.orders, Order(f"o{n}", supplier)).apply(state)
    return state


def _sent(state: Orders) -> list[bool]:
    return [o.sent for o in state.own(Orders.orders)]


def test_a_refused_batch_keeps_the_orders_sent_before_the_refusal():
    state = _orders("delivers", "refuses", "delivers")
    outcome = state.perform(SendOrders(Batch(("o0", "o1", "o2"))))
    assert outcome == Refusal("a supplier refused the delivery", 424)
    assert _sent(state) == [True, False, False]


def test_a_refusal_with_nothing_kept_changes_nothing():
    state = _orders("delivers", "refuses")
    outcome = state.perform(SendOrdersSilently(Batch(("o0", "o1"))))
    assert outcome == Refusal("a supplier refused the delivery", 424)
    assert _sent(state) == [False, False]


def test_a_dry_run_of_a_refusal_leaves_the_state_alone():
    state = _orders("delivers", "refuses")
    assert state.explain(SendOrders(Batch(("o0", "o1")))) is delivery_refused
    assert _sent(state) == [False, False]


def test_an_accepted_batch_sends_every_order():
    state = _orders("delivers", "delivers")
    assert isinstance(state.perform(SendOrders(Batch(("o0", "o1")))), Done)
    assert _sent(state) == [True, True]


crashes = Defect[Batch, Orders]("internal error", lambda a, s, by: True, over=delivery_refused)


class SendAndCrash(Send):
    defects = (crashes,)


@dataclass(frozen=True)
class SendOrdersAndCrash(SendOrders):
    carries: ClassVar[type[Action[Any, Any]]] = SendAndCrash


def test_a_defect_over_a_keeping_refusal_remembers_what_the_refusal_meant_to_keep():
    state = _orders("delivers", "refuses")
    flawed = state.perform(SendOrdersAndCrash(Batch(("o0", "o1"))))
    assert isinstance(flawed, Flawed)
    assert flawed.meant == Refusal("a supplier refused the delivery", 424)
    state.adopt(flawed)
    assert _sent(state) == [True, False]


def test_the_action_names_what_a_refusal_keeps():
    assert "keeps what it did before it refused" in Send.explain()
