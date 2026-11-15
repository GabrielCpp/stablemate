"""An event delivered before the service's handler: the run places it, reads the watch until it lands, and places it again."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from ostler.book import Arrange
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
