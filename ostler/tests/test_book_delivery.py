"""An event delivered before the service's handler: the run places it, reads the watch until it lands, and places it again."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from ostler.book import Again, Arrange, BookError
from ostler.book.runner import Deliveries, Landings, perform

from book_desk import Desk, DeskSurface, TicketChanged, ToQueue
from book_fakes import Counter as Tally

DAY = date(2026, 11, 14)


class Counter(Tally):
    def counts(self, request: object) -> bool:
        return isinstance(request, (Opens, Told))


class Opens(Arrange[str]):
    does = "A customer opens a ticket."
    heard = TicketChanged
    reads = ("ticket_id", "snapshot.priority", "snapshot.team")

    def detail(self, model: Any) -> dict[str, Any]:
        return {"ticket_id": self.of, "by": "customer", "snapshot": {"priority": "high", "team": "a"}}


class Told(Arrange[str]):
    does = "A ticket is opened and the surface is told."
    heard = TicketChanged


class Forgetful(Opens):
    def detail(self, model: Any) -> dict[str, Any]:
        return {"ticket_id": self.of, "by": "customer", "snapshot": {"priority": "high"}}


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Landings, "longest", 0)
    monkeypatch.setattr(Landings, "missed", False)
    monkeypatch.setattr(Deliveries, "role", None)


def _desk(bug: str | None = None) -> tuple[Desk, DeskSurface, ToQueue]:
    desk = Desk(bug)
    delivery = ToQueue(desk)
    Deliveries.begin(delivery)
    return desk, DeskSurface(desk), delivery


def test_a_delivered_hearing_lands_and_its_step_passes_with_no_other_service_called():
    desk, surface, delivery = _desk()
    step = Opens("T-1")
    result = perform(step, step, Counter(DAY), surface)
    assert result.ok, result.note
    assert surface.performed == []
    assert delivery.placed[0]["ticket_id"] == "T-1"
    assert desk.priorities == {"T-1": "high"}


def test_a_hearing_with_no_detail_is_still_performed_by_the_books_surface():
    desk, surface, delivery = _desk()
    step = Told("T-2")
    result = perform(step, step, Counter(DAY), surface)
    assert result.ok, result.note
    assert surface.performed == [step]
    assert delivery.placed == []


def test_a_detail_that_lacks_a_field_the_hearing_reads_fails_the_step_and_names_the_path():
    desk, surface, delivery = _desk()
    step = Forgetful("T-3")
    result = perform(step, step, Counter(DAY), surface)
    assert not result.ok
    assert "detail.snapshot.team" in result.note
    assert delivery.placed == []
    assert desk.count == 0


class Trails(Opens):
    does = "A customer opens a ticket. Each delivery adds a line to the trail."
    repeat = Again("each delivery adds a line to the trail, the trail is a log of deliveries")


def test_a_second_delivery_that_changes_nothing_passes():
    desk, surface, delivery = _desk()
    step = Opens("T-4")
    result = perform(step, step, Counter(DAY), surface)
    assert result.ok, result.note
    assert len(delivery.placed) == 2
    assert delivery.placed[0] == delivery.placed[1]
    assert desk.count == 1


def test_a_second_delivery_the_handler_applies_again_fails_and_says_so():
    desk, surface, delivery = _desk("applies-again")
    step = Opens("T-5")
    result = perform(step, step, Counter(DAY), surface)
    assert not result.ok
    assert "second delivery was applied again" in result.note
    assert desk.count == 2


def test_a_hearing_that_declares_its_second_delivery_applies_again_passes_when_it_does():
    desk, surface, delivery = _desk("applies-again")
    step = Trails("T-6")
    result = perform(step, step, Counter(DAY), surface)
    assert result.ok, result.note
    assert len(delivery.placed) == 2
    assert desk.count == 2


def test_an_again_with_no_reason_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Again has no reason"):
        Again("  ")


def test_the_run_counts_its_second_deliveries_on_one_line():
    desk, surface, delivery = _desk()
    model = Counter(DAY)
    for ticket in ("T-7", "T-8"):
        step = Opens(ticket)
        perform(step, step, model, surface)
    assert Deliveries.line() == "repeats: 2 delivered, 0 applied again as declared, 0 fail"


def test_a_run_that_delivered_no_hearing_prints_no_repeats_line():
    _desk()
    assert Deliveries.line() == ""
