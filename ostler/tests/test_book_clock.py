"""An action the service's clock causes: what the format refuses and what a search finds."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ostler.book import Action, Answer, Arrange, BookError, Endpoint
from ostler.book.check import clock_faults
from ostler.book.domain import State
from ostler.book.search import search

from book_desk import Breach, Breached
from test_book_web import _service


def test_an_action_the_clock_causes_that_also_hears_headers_is_refused():
    with pytest.raises(BookError, match="Late is caused by the clock .* and hears headers"):

        class Late(Action[int, State]):
            clock = "the due time goes by"
            hears = True


class Overdue(Endpoint):
    path = "/overdue"
    answers = (Answer(200, None, "ok"),)
    carries = Breach
    does = "Reports an overdue ticket."


class Hears(Arrange[str]):
    does = "The queue delivers a breach."
    carries = Breach
    heard = Breached

    def detail(self, model):
        return {}


def test_an_endpoint_that_carries_a_clocked_action_is_a_finding_that_says_what_to_write_instead():
    service = replace(_service(languages=("en",)), new_model=State, endpoints=(Overdue,))
    [found] = clock_faults(service)
    assert found.name == "endpoint Overdue"
    assert "carries Breach, which the clock causes (\"the ticket's due time goes by\")" in found.problem
    assert "carry it from an Arrange" in found.problem


def test_an_outside_event_that_hears_an_event_and_carries_a_clocked_action_is_a_finding():
    service = replace(_service(languages=("en",)), new_model=State, outside=(Hears,))
    [found] = clock_faults(service)
    assert found.name == "outside Hears"
    assert "hears ticket.breached and carries Breach" in found.problem
    assert "split it in two" in found.problem


def test_a_book_that_carries_its_clocked_action_from_an_arrange_has_no_such_finding():
    from book_desk import Breaches

    service = replace(_service(languages=("en",)), new_model=State, outside=(Breaches,))
    assert clock_faults(service) == []


def test_a_search_for_a_word_of_the_moment_finds_the_clocked_action():
    service = replace(_service(languages=("en",)), new_model=State, endpoints=(Overdue,))
    hits = search(service, "book_desk", "due time goes by", "action")
    assert [item.name for item, _ in hits] == ["Breach"]
    assert "clock: the ticket's due time goes by" in hits[0][0].lines
