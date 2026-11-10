"""What goes on the wire for a declared shape, and how an app id is spoken as the model's."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from ostler.book import BookError, Field, Id, Int, List, Object, Str
from ostler.book.http import Identities, canonical, real_id


@dataclass
class Item:
    sku: str
    quantity: int = 1


@dataclass
class Order:
    item: Item
    lines: list[Item] = field(default_factory=list)
    note: str | None = None


@dataclass
class Trip:
    from_: str
    to: str


ITEM = Object("Item", sku=Field(Str()), quantity=Field(Int()))
ORDER = Object("Order", item=Field(ITEM), lines=Field(List(ITEM)), note=Field(Str(), required=False))
TRIP = Object("Trip", **{"from": Field(Str()), "to": Field(Str())})


def test_a_nested_dataclass_is_packed_by_the_declared_shape():
    packed = ORDER.pack(Order(Item("a-1", 2)))
    assert packed == {"item": {"sku": "a-1", "quantity": 2}, "lines": []}


def test_a_list_of_dataclasses_is_packed_item_by_item():
    packed = ORDER.pack(Order(Item("a-1"), [Item("b-2", 3), Item("c-3")]))
    assert packed["lines"] == [{"sku": "b-2", "quantity": 3}, {"sku": "c-3", "quantity": 1}]


def test_a_field_left_none_is_left_out_of_the_body():
    assert "note" not in ORDER.pack(Order(Item("a-1")))
    assert ORDER.pack(Order(Item("a-1"), note="soon"))["note"] == "soon"


def test_a_keyword_field_goes_on_the_wire_without_its_underscore():
    assert TRIP.pack(Trip("Lyon", "Nice")) == {"from": "Lyon", "to": "Nice"}


def test_a_quoted_app_id_is_spoken_as_the_models():
    ids = Identities()
    ids.learn(Item, "t1", "9f2c-77")
    assert ids.spoken("no todo '9f2c-77' here") == "no todo 't1' here"


def test_a_longer_id_that_contains_the_app_id_is_left_alone():
    ids = Identities()
    ids.learn(Item, "t1", "9f2c-77")
    for text in ("no todo '9f2c-770'", "no todo 'x9f2c-77'", "no todo '9f2c-77-b'"):
        assert ids.spoken(text) == text


def test_an_id_the_app_gave_as_the_models_own_is_not_rewritten():
    ids = Identities()
    ids.learn(Item, "same", "same")
    assert ids.spoken("no todo 'same'") == "no todo 'same'"


def test_a_keyword_field_of_a_record_is_read_off_its_underscored_attribute():
    app = canonical(TRIP, {"from": "Oslo", "to": "Rome"}, app=True, ids=None, where="Trip")
    model = canonical(TRIP, Trip(from_="Oslo", to="Rome"), app=False, ids=None, where="Trip")
    assert app == model


class Team:
    pass


MINTED = Id(Team, Str(), minted="one cell owns it")


def test_a_minted_id_goes_out_as_the_models_value_and_a_suffix_that_stays():
    ids = Identities()
    first = real_id(MINTED, "core", ids, "Send")
    assert first.startswith("core-")
    assert len(first) == len("core-") + 8
    assert real_id(MINTED, "core", ids, "Send") == first


def test_a_minted_id_differs_between_two_clients():
    one, other = Identities(), Identities()
    assert real_id(MINTED, "core", one, "Send") != real_id(MINTED, "core", other, "Send")


def test_an_answer_with_a_minted_id_reads_back_as_the_models_value():
    ids = Identities()
    sent = real_id(MINTED, "core", ids, "Send")
    body = Object("Reply", team=Field(MINTED))
    assert canonical(body, {"team": sent}, app=True, ids=ids, where="Reply") == canonical(body, SimpleNamespace(team="core"), app=False, ids=None, where="Reply")


def test_an_id_made_by_two_people_is_refused():
    with pytest.raises(BookError, match="pick who makes the value"):
        Id(Team, Str(), strangers="a person chose it", minted="one cell owns it")


def test_a_blank_minted_value_is_sent_as_it_is():
    assert real_id(MINTED, "", Identities(), "body.team") == ""


def test_a_minted_value_at_a_length_bound_stays_at_it():
    bounded = Id(Team, Str(max_len=20), minted="one cell owns it")
    ids = Identities()
    assert len(real_id(bounded, "x" * 20, ids, "body.team")) == 20
    assert len(real_id(bounded, "y" * 21, ids, "body.team")) == 21
    assert len(real_id(bounded, "desk", ids, "body.team")) == len("desk") + 9


def test_a_minted_name_in_another_case_is_the_same_value_in_that_case():
    ids = Identities()
    made = real_id(MINTED, "Desk", ids, "body.team")
    assert real_id(MINTED, "DESK", ids, "body.team") == made.upper()
    assert real_id(MINTED, "desk", ids, "body.team") == made.lower()
    assert ids.model_of(Team, made.upper()) == "DESK"
