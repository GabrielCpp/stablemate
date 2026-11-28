"""An emission proven by a tap: the run reads the events the environment carries and judges the ones about records it made."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pytest

from ostler.book import BookError, Bus, Delivery
from ostler.book import tapping
from ostler.book.runner import perform
from ostler.book.tapping import Deliveries, Landings

from book_desk import Breaches, Desk, Emitter, Lapses, Opens, OpensAndAudits, OpensQuietly, ScanTap, Scanner, Tap, Tickets, ToQueue, Upserts, Writes

DAY = date(2026, 11, 14)


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(Landings, "longest", 0)
    monkeypatch.setattr(Landings, "missed", False)
    monkeypatch.setattr(Deliveries, "role", None)
    yield
    Deliveries.close()
    Deliveries.begin(None)


def _run(step: Any, bug: str | None = None, role: Delivery | None = None) -> tuple[Any, Tap, Tickets]:
    tap = Tap()
    Deliveries.begin(role if role is not None else tap)
    model = Tickets(DAY)
    result = perform(step, step, model, Emitter(tap, bug))
    return result, tap, model


def test_an_action_that_emits_passes_when_the_event_about_its_record_arrives_with_what_the_book_announces():
    result, tap, _ = _run(Opens("T-1"))
    assert result.ok, result.note
    assert tap.opened == 1


def test_an_action_that_stops_emitting_fails_its_step_and_the_note_says_the_tap_read_none():
    result, tap, _ = _run(Opens("T-2"), bug="silent")
    assert not result.ok
    assert "Open should emit ticket.changed about a record this run made; the tap read none in" in result.note
    assert "reads" in result.note


def test_an_emitted_field_that_differs_from_the_book_fails_the_step_and_the_note_names_the_path_and_both_values():
    result, tap, _ = _run(Opens("T-3"), bug="wrong")
    assert not result.ok
    assert "snapshot.priority tapped 'low', the book says 'high'" in result.note


def test_an_event_about_a_record_the_run_did_not_make_is_ignored():
    result, tap, _ = _run(Opens("T-4"))
    assert result.ok, result.note
    assert Deliveries.buffer == []


def test_an_action_whose_announces_returns_none_passes_on_arrival_alone():
    result, tap, _ = _run(OpensQuietly("T-5"), bug="wrong")
    assert result.ok, result.note


def test_an_event_about_a_stranger_alone_is_not_an_arrival():
    result, tap, _ = _run(OpensQuietly("T-6"), bug="stranger")
    assert not result.ok
    assert "the tap read none" in result.note


def test_the_run_counts_its_emissions_on_one_line():
    tap = Tap()
    Deliveries.begin(tap)
    model = Tickets(DAY)
    surface = Emitter(tap)
    for ticket in ("T-7", "T-8"):
        perform(step := Opens(ticket), step, model, surface)
    assert Deliveries.line() == "emissions: 2 proven, 0 fail, 0 unproven"


def test_a_failed_emission_is_counted_as_failed():
    _run(Opens("T-9"), bug="silent")
    assert Deliveries.line() == "emissions: 0 proven, 1 fail, 0 unproven"


def test_a_run_with_no_emitting_action_prints_no_emissions_line():
    Deliveries.begin(Tap())
    assert Deliveries.line() == ""


def test_an_environment_whose_delivery_cannot_tap_leaves_an_emission_unproven_and_passes_the_step():
    result, _, _ = _run(Opens("T-10"), role=ToQueue(Desk()))
    assert result.ok, result.note
    assert Deliveries.line() == "emissions: 0 proven, 0 fail, 1 unproven"


def test_an_environment_that_names_no_delivery_leaves_an_emission_unproven_and_passes_the_step():
    tap = Tap()
    Deliveries.begin(None)
    step = Opens("T-11")
    result = perform(step, step, Tickets(DAY), Emitter(tap))
    assert result.ok, result.note
    assert Deliveries.line() == "emissions: 0 proven, 0 fail, 1 unproven"


def test_the_tap_opens_once_for_a_run_and_closes_on_close():
    tap = Tap()
    Deliveries.begin(tap)
    model = Tickets(DAY)
    surface = Emitter(tap)
    for ticket in ("T-12", "T-13"):
        perform(step := Opens(ticket), step, model, surface)
    assert tap.opened == 1
    assert tap.closed == 0
    Deliveries.close()
    assert tap.closed == 1


def test_the_tap_takes_over_sigterm_while_open_and_gives_it_back_on_close():
    before = signal.getsignal(signal.SIGTERM)
    _run(Opens("T-14"))
    assert signal.getsignal(signal.SIGTERM) == Deliveries.terminated
    with pytest.raises(SystemExit):
        Deliveries.terminated(signal.SIGTERM, None)
    Deliveries.close()
    assert signal.getsignal(signal.SIGTERM) == before


FAILING_RUN = """
import sys
from datetime import date
from book_desk import Emitter, Opens, Tap, Tickets
from ostler.book.runner import perform
from ostler.book.tapping import Deliveries

class Marked(Tap):
    def close_tap(self):
        open(sys.argv[1], "w").write("closed")

tap = Marked()
Deliveries.begin(tap)
step = Opens("T-15")
result = perform(step, step, Tickets(date(2026, 11, 14)), Emitter(tap, "silent"))
assert not result.ok
raise RuntimeError("the run fails")
"""


def test_the_tap_is_closed_when_the_run_fails(tmp_path: Path):
    mark = tmp_path / "mark"
    here = str(Path(__file__).parent)
    done = subprocess.run([sys.executable, "-c", FAILING_RUN, str(mark)], env={**os.environ, "PYTHONPATH": here},
                          capture_output=True, text=True, check=False)
    assert done.returncode == 1
    assert "the run fails" in done.stderr
    assert mark.read_text() == "closed"


class Events:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    def put_rule(self, **kw: Any) -> dict[str, str]:
        self.calls.append(("put_rule", kw))
        return {"RuleArn": "arn:rule"}

    def put_targets(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("put_targets", kw))
        return {}

    def remove_targets(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("remove_targets", kw))
        return {}

    def delete_rule(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("delete_rule", kw))
        return {}


class Queues:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls
        self.inbox: list[dict[str, Any]] = []

    def create_queue(self, **kw: Any) -> dict[str, str]:
        self.calls.append(("create_queue", kw))
        return {"QueueUrl": "http://q/" + kw["QueueName"]}

    def get_queue_attributes(self, **kw: Any) -> dict[str, Any]:
        return {"Attributes": {"QueueArn": "arn:queue"}}

    def set_queue_attributes(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("set_queue_attributes", kw))
        return {}

    def receive_message(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("receive_message", kw))
        out, self.inbox = self.inbox, []
        return {"Messages": out}

    def delete_message(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("delete_message", kw))
        return {}

    def delete_queue(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("delete_queue", kw))
        return {}


def _bus() -> tuple[Bus, Queues, list[tuple[str, dict[str, Any]]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    queues = Queues(calls)
    return Bus("zeta-bus", client=Events(calls), queues=queues), queues, calls


def test_the_bus_variant_creates_a_queue_a_catch_all_rule_and_a_target_and_removes_all_three_on_close():
    bus, queues, calls = _bus()
    bus.open_tap()
    names = [c[0] for c in calls]
    assert names == ["create_queue", "put_rule", "set_queue_attributes", "put_targets"]
    queue = calls[0][1]["QueueName"]
    assert queue.startswith("ostler-tap-") and len(queue) == len("ostler-tap-") + 8
    rule = calls[1][1]
    assert rule["Name"] == queue and rule["EventBusName"] == "zeta-bus"
    assert json.loads(rule["EventPattern"]) == {"source": [{"prefix": ""}]}
    assert calls[3][1]["Targets"] == [{"Id": "tap", "Arn": "arn:queue"}]
    assert "arn:rule" in calls[2][1]["Attributes"]["Policy"]
    bus.close_tap()
    assert [c[0] for c in calls[4:]] == ["remove_targets", "delete_rule", "delete_queue"]
    assert calls[5][1] == {"Name": queue, "EventBusName": "zeta-bus"}
    assert calls[6][1] == {"QueueUrl": "http://q/" + queue}


def test_the_bus_variant_reads_ten_at_a_time_deletes_what_it_read_and_decodes_the_envelope():
    bus, queues, calls = _bus()
    bus.open_tap()
    queues.inbox = [{"ReceiptHandle": "h1", "Body": json.dumps({"detail-type": "ticket.changed", "detail": {"ticket_id": "T-1"}})},
                    {"ReceiptHandle": "h2", "Body": json.dumps({"detail-type": "ticket.changed", "detail": json.dumps({"ticket_id": "T-2"})})}]
    assert bus.tapped() == [("ticket.changed", {"ticket_id": "T-1"}), ("ticket.changed", {"ticket_id": "T-2"})]
    read = [c for c in calls if c[0] == "receive_message"][0][1]
    assert read["MaxNumberOfMessages"] == 10 and read["WaitTimeSeconds"] == 0
    assert [c[1]["ReceiptHandle"] for c in calls if c[0] == "delete_message"] == ["h1", "h2"]


def test_the_bus_variant_removes_what_it_made_when_opening_fails_half_way(monkeypatch: pytest.MonkeyPatch):
    bus, queues, calls = _bus()

    def refuse(**kw: Any) -> dict[str, Any]:
        raise RuntimeError("no")

    monkeypatch.setattr(queues, "set_queue_attributes", refuse)
    with pytest.raises(RuntimeError):
        bus.open_tap()
    assert [c[0] for c in calls] == ["create_queue", "put_rule", "delete_rule", "delete_queue"]


def test_the_bus_variant_names_the_aws_extra_when_boto3_is_missing_for_the_tap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(BookError, match=r"install the aws extra of ostler"):
        Bus("zeta-bus").open_tap()


def _clocked(scanning: bool = True) -> tuple[ScanTap, Scanner, Tickets]:
    tap = ScanTap()
    Deliveries.begin(tap)
    model = Tickets(DAY)
    surface = Scanner(tap, scanning)
    surface.start()
    return tap, surface, model


def test_a_step_that_carries_a_clocked_action_sends_nothing_and_proves_its_emission_from_the_tap():
    tap, surface, model = _clocked()
    try:
        for step in (Writes("T-20"), Lapses("T-20"), Breaches("T-20")):
            result = perform(step, step, model, surface)
            assert result.ok, result.note
    finally:
        surface.stop()
    assert [type(s) for s in surface.performed] == [Writes, Lapses]
    assert Deliveries.line() == "emissions: 1 proven, 0 fail, 0 unproven"


def test_a_clocked_action_whose_scan_never_runs_fails_its_step_and_the_note_says_the_tap_read_none(monkeypatch: pytest.MonkeyPatch):
    tap, surface, model = _clocked(scanning=False)
    monkeypatch.setattr(tapping, "RETAKES", 20)
    for step in (Writes("T-21"), Lapses("T-21")):
        assert perform(step, step, model, surface).ok
    step = Breaches("T-21")
    result = perform(step, step, model, surface)
    assert not result.ok
    assert "Breach should emit ticket.breached about a record this run made; the tap read none in 20 reads" in result.note


def test_a_clocked_action_in_an_environment_that_names_no_delivery_leaves_its_emission_unproven():
    surface = Scanner(ScanTap())
    model = Tickets(DAY)
    Deliveries.begin(None)
    for step in (Writes("T-22"), Lapses("T-22"), Breaches("T-22")):
        assert perform(step, step, model, surface).ok
    assert Deliveries.line() == "emissions: 0 proven, 0 fail, 1 unproven"


def test_emits_when_reads_state_before_reduce_and_skips_tap_and_unproven_when_false():
    tap = Tap()
    Deliveries.begin(tap)
    model = Tickets(DAY)
    surface = Emitter(tap)
    first = perform(step := Upserts("T-23"), step, model, surface)
    second = perform(step := Upserts("T-23"), step, model, surface)
    assert first.ok, first.note
    assert second.ok, second.note
    assert Deliveries.line() == "emissions: 1 proven, 0 fail, 0 unproven"

    Deliveries.begin(None)
    model_no_tap = Tickets(DAY)
    surface_no_tap = Emitter(Tap())
    assert perform(step := Upserts("T-24"), step, model_no_tap, surface_no_tap).ok
    assert perform(step := Upserts("T-24"), step, model_no_tap, surface_no_tap).ok
    assert Deliveries.line() == "emissions: 0 proven, 0 fail, 1 unproven"


def test_multi_event_emissions_canonicalize_each_buffered_event_against_its_own_schema():
    result, _, _ = _run(OpensAndAudits("T-25"))
    assert result.ok, result.note
    assert Deliveries.line() == "emissions: 2 proven, 0 fail, 0 unproven"


