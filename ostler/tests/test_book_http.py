"""What goes on the wire for a declared shape, and how an app id is spoken as the model's."""

from __future__ import annotations

from dataclasses import dataclass, field

from ostler.book import Field, Int, List, Object, Str
from ostler.book.http import Identities, canonical


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
