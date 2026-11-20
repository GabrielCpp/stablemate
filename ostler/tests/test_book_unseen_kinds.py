"""What `Unseen` accepts for each kind of stated element, and what it refuses."""

from __future__ import annotations

from typing import Any, cast

import pytest

from ostler.book import Answer, Endpoint, Scene
from ostler.book.errors import BookError
from ostler.book.witness import Because, Unseen

from book_fakes import Ghost, Haunt, MISSING, Put


class Ping(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)


SCENE = Scene("empty", "nothing on it", lambda today: ())

ELEMENTS = [("outside happening", Ghost, "Ghost"), ("action", Haunt, "Haunt"), ("rule", MISSING, "not-on-the-shelf"),
            ("scene", SCENE, "empty")]


def a(kind: str) -> str:
    return "an" if kind[0] in "aeiou" else "a"


def test_the_old_positional_form_still_loads_for_an_endpoint():
    declared = Unseen(Ping, "401", Because.SHARED_GATE, "another endpoint shows it")
    assert declared.of is Ping
    assert declared.item == "401"
    assert declared.because is Because.SHARED_GATE
    assert declared.key == (Ping, "401")
    assert declared.kind == "endpoint"


def test_the_item_can_be_named_in_the_new_form_of_an_endpoint():
    assert Unseen(of=Ping, item="401", because=Because.RUNTIME, why="a reason").key == (Ping, "401")


@pytest.mark.parametrize("kind, element, name", ELEMENTS)
def test_every_other_kind_is_declared_without_an_item(kind, element, name):
    declared = Unseen(element, Because.OUTSIDE, "only a system outside the app does it")
    assert declared.kind == kind
    assert declared.item == ""
    assert declared.name == name
    assert declared.key == (kind, name)


@pytest.mark.parametrize("kind, element, name", ELEMENTS)
def test_every_other_kind_refuses_an_item(kind, element, name):
    with pytest.raises(BookError, match=f"{a(kind)} {kind} takes no item"):
        Unseen(element, "401", Because.RUNTIME, "a reason")


def test_an_endpoint_without_an_item_is_told_what_to_write():
    with pytest.raises(BookError, match=r"an endpoint needs the answer it leaves unseen: write Unseen\(Ping, '401', Because"):
        Unseen(cast(Any, Ping), Because.RUNTIME, "a reason")


def test_a_value_that_is_no_element_is_refused():
    with pytest.raises(BookError, match="an endpoint, an outside happening, an action, a rule or a scene"):
        Unseen(cast(Any, Put()), Because.RUNTIME, "a reason")


def test_a_short_form_without_a_because_is_refused():
    with pytest.raises(BookError, match="give a Because"):
        Unseen(Ghost, cast(Any, "no time"), "a reason")


@pytest.mark.parametrize("because", [Because.NEVER_FILLED, Because.TEST_HOOK, Because.SHARED_GATE])
@pytest.mark.parametrize("kind, element, name", ELEMENTS)
def test_an_endpoint_only_reason_is_refused_for_the_other_kinds(kind, element, name, because):
    with pytest.raises(BookError, match=f"{a(kind)} {kind} is declared with Because.RUNTIME, OUTSIDE or NO_ACCOUNT"):
        Unseen(element, because, "a reason")


@pytest.mark.parametrize("because", [Because.RUNTIME, Because.OUTSIDE, Because.NO_ACCOUNT])
@pytest.mark.parametrize("kind, element, name", ELEMENTS)
def test_the_three_reasons_are_legal_for_the_other_kinds(kind, element, name, because):
    assert Unseen(element, because, "a reason").because is because


def test_never_filled_stays_legal_for_every_item_of_an_endpoint():
    for item in ("401", "200: a.b", "inputs"):
        assert Unseen(Ping, item, Because.NEVER_FILLED, "a reason").item == item


def test_a_blank_why_is_refused_for_every_kind():
    with pytest.raises(BookError, match="say why"):
        Unseen(Ghost, Because.RUNTIME, " ")


def test_a_book_that_reads_the_element_by_its_old_name_still_loads():
    assert Unseen(Ping, "401", Because.SHARED_GATE, "another endpoint shows it").endpoint is Ping
