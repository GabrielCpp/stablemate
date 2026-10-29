"""`Qa` against outside resources: borrowing through a request step, giving back however the scenario ends, reading an observation until it holds, and a resource that is absent."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from booking_fake import BookingFake, write_booking_book
from ostler import model
from ostler.qa import book_fixtures as qa_book_fixtures
from ostler.qa.attribution import CheckEvidence, attribute, signatures
from ostler.qa.drivers import run_pending_releases
from test_qa_harness_book_fixtures import PLAN_HEADER, _harness

TOKEN = "s3cret-booking-token"

WALKING_SKELETON = '''\
import urllib.request

@scenario(target=api, mechanism="live", covers=["ac:1"])
def plays_and_sees_the_recording(qa: Qa) -> None:
    """Borrow the camera, play a video, and wait for the recording."""
    qa.fixture("camera-booked")
    urllib.request.urlopen(urllib.request.Request("{camera}/play", data=b"{}", method="POST")).close()
    seen = qa.observe("camera", "recordings", within=10, until=[("count", {"subject": "items", "equals": 1})])
    qa.check("one recording", len(seen.json()["items"]) == 1)
'''

RAISES = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def raises_while_holding_the_camera(qa: Qa) -> None:
    """Borrow, then crash."""
    qa.fixture("camera-booked")
    raise RuntimeError("the scenario blew up")
'''

FAILS = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def fails_while_holding_the_camera(qa: Qa) -> None:
    """Borrow, then fail a check."""
    qa.fixture("camera-booked")
    qa.check("never true", False)
'''

BORROWS = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def borrows_an_absent_camera(qa: Qa) -> None:
    """Borrow from a booking service nobody listens on."""
    qa.fixture("camera-booked")
    qa.check("unreachable", True)
'''

OBSERVES = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def waits_for_a_recording(qa: Qa) -> None:
    """Wait for a recording that never comes."""
    seen = qa.observe("camera", "recordings", within=1, until=[("count", {"subject": "items", "equals": 1})])
    qa.check("one recording", len(seen.json()["items"]) == 1)
'''

LATE = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def waits_for_a_late_recording(qa: Qa) -> None:
    """Wait for a recording that arrives after the first read."""
    seen = qa.observe("camera", "recordings", within=10, until=[("count", {"subject": "items", "equals": 1})])
    qa.check("one recording", len(seen.json()["items"]) == 1)
'''


@pytest.fixture
def fake() -> Iterator[BookingFake]:
    server = BookingFake().start()
    yield server
    server.stop()


@pytest.fixture
def context(tmp_path: Path) -> dict:
    (tmp_path / "docs").mkdir()
    write_booking_book(tmp_path)
    graph = model.load(tmp_path)
    return {
        "root": str(tmp_path), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa"), "lap_dir": "",
        "book_fixtures": qa_book_fixtures.resolved(graph), "resources": qa_book_fixtures.resolved_resources(graph),
    }


def _go(
    tmp_path: Path, body: str, scenario_id: str, context: dict, fake: BookingFake | None, *, booking_up: bool = True,
) -> tuple[int, str, list[dict]]:
    module = tmp_path / "qa_plan.py"
    module.write_text(PLAN_HEADER + body.replace("{camera}", fake.url if fake else ""), encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "CAMERA_BOOKING_TOKEN": TOKEN}
    if fake is not None:
        env["CAMERA_URL"] = fake.url
        env["BOOKING_URL"] = fake.url if booking_up else "http://127.0.0.1:1"
    return _harness("run", str(module), scenario_id, json.dumps(context), env=env, records_to=tmp_path / "records.jsonl")


def _of(records: list[dict], kind: str) -> list[dict]:
    return [r for r in records if r.get("type") == kind]


def test_a_scenario_borrows_plays_observes_and_gives_the_camera_back(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, output, records = _go(tmp_path, WALKING_SKELETON, "plays-and-sees-the-recording", context, fake)
    assert code == 0, (output, records)
    assert fake.leases == {}
    [pending] = _of(records, "release-pending")
    assert pending["path"] == "/leases/1"
    [released] = _of(records, "release")
    assert released["ok"] is True
    [observed] = _of(records, "observe")
    assert observed["polls"] >= 2


def test_the_camera_goes_back_after_the_scenario_raises(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, output, records = _go(tmp_path, RAISES, "raises-while-holding-the-camera", context, fake)
    assert code != 0, output
    assert fake.leases == {}
    assert [r["ok"] for r in _of(records, "release")] == [True]


def test_the_camera_goes_back_after_a_check_fails(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, output, records = _go(tmp_path, FAILS, "fails-while-holding-the-camera", context, fake)
    assert code != 0, output
    assert fake.leases == {}
    assert [r["ok"] for r in _of(records, "release")] == [True]


def test_an_absent_booking_service_is_a_capability_gap_naming_the_resource(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, _output, records = _go(tmp_path, BORROWS, "borrows-an-absent-camera", context, fake, booking_up=False)
    assert code != 0
    [fault] = _of(records, "fixture_fault")
    assert fault["fault_class"] == "capability"
    assert fault["fixture"] == "camera-booking"
    assert fake.leases == {}
    evidence = CheckEvidence.model_validate(
        {"label": "a check", "passed": False, "fault": {"fault_class": "capability", "fixture": fault["fixture"], "page": ""}})
    assert signatures([(attribute(evidence), "no camera")])[0].text() == "gapped: camera booking absent"


def test_observe_polls_until_the_late_recording_arrives(tmp_path: Path, fake: BookingFake, context: dict) -> None:


    threading.Timer(1.2, lambda: fake.recordings.append({"video": "late"})).start()
    code, output, records = _go(tmp_path, LATE, "waits-for-a-late-recording", context, fake)
    assert code == 0, (output, records)
    [observed] = _of(records, "observe")
    assert observed["polls"] >= 2


def test_observe_fails_with_the_last_read_when_it_never_holds(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, output, records = _go(tmp_path, OBSERVES, "waits-for-a-recording", context, fake)
    assert code != 0
    [check] = _of(records, "assert")
    assert check["passed"] is False


def test_the_credential_reaches_the_resource_and_nothing_the_scenario_wrote(tmp_path: Path, fake: BookingFake, context: dict) -> None:
    code, output, records = _go(tmp_path, FAILS, "fails-while-holding-the-camera", context, fake)
    assert code != 0
    assert {auth for method, _path, auth in fake.requests if method == "POST"} == {f"Bearer {TOKEN}"}
    assert TOKEN not in output
    assert TOKEN not in "\n".join(json.dumps(r) for r in records)


def test_a_run_that_died_still_gives_the_camera_back(tmp_path: Path, fake: BookingFake, context: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    fake.leases["7"] = "camera-1"
    records = [{"type": "release-pending", "fixture": "camera-booked", "step": 1, "resource": "camera-booking",
                "method": "DELETE", "path": "/leases/7"}]
    run_pending_releases(records, context["resources"], {"BOOKING_URL": fake.url, "CAMERA_BOOKING_TOKEN": TOKEN})
    assert fake.leases == {}
    assert ("DELETE", "/leases/7", f"Bearer {TOKEN}") in fake.requests


def test_a_release_the_scenario_already_sent_is_not_sent_again(fake: BookingFake, context: dict) -> None:
    fake.leases["7"] = "camera-1"
    records = [
        {"type": "release-pending", "fixture": "camera-booked", "step": 1, "resource": "camera-booking",
         "method": "DELETE", "path": "/leases/7"},
        {"type": "release", "fixture": "camera-booked", "step": 1, "ok": True},
    ]
    run_pending_releases(records, context["resources"], {"BOOKING_URL": fake.url, "CAMERA_BOOKING_TOKEN": TOKEN})
    assert fake.leases == {"7": "camera-1"}
