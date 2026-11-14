"""Events a service emits and hears: declared once, followed by name across books."""

from __future__ import annotations

from typing import Any, cast

import pytest

from ostler.book import Action, Arrange, BookError, Event, Field, Object, Str


def test_an_event_with_no_docstring_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Silent has no docstring"):

        class Silent(Event):
            name = "ticket.changed"
            detail = Object(actor=Field(Str()))


def test_an_event_with_no_name_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Nameless has no name"):

        class Nameless(Event):
            """Something happened."""

            detail = Object(actor=Field(Str()))


def test_an_event_with_no_detail_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Empty has no detail"):

        class Empty(Event):
            """Something happened."""

            name = "ticket.changed"


def test_an_outside_event_that_reads_fields_and_hears_no_event_is_refused():
    with pytest.raises(BookError, match="Opens reads .* hears no event"):

        class Opens(Arrange[int]):
            does = "A customer opens a ticket."
            reads = ("ticket_id",)


def test_an_action_that_emits_something_that_is_not_an_event_is_refused():
    with pytest.raises(BookError, match="Transition emits .* not an Event"):

        class Transition(Action):
            emits = cast(Any, ("ticket.changed",))
