"""`book_fixtures` walks resource pages and request steps into the harness's `context["resources"]` and `context["book_fixtures"]`."""

from __future__ import annotations

import json
from pathlib import Path

from booking_fake import write_booking_book
from ostler.model import load
from ostler.qa import book_fixtures


def test_a_request_step_resolves_to_a_method_a_path_a_body_and_its_resource(repo: Path) -> None:
    write_booking_book(repo)
    steps = book_fixtures.resolved(load(repo))["camera-booked"]["steps"]
    take, give_back = steps
    assert (take["kind"], take["on"], take["request"], take["body"]) == (
        "borrow", "camera-booking", {"method": "POST", "path": "/leases"}, '{"device": "camera-1"}')
    assert (give_back["kind"], give_back["request"]) == ("release", {"method": "DELETE", "path": "/leases/$lease"})


def test_a_resource_resolves_to_its_reach_probe_and_observations(repo: Path) -> None:
    write_booking_book(repo)
    resources = book_fixtures.resolved_resources(load(repo))
    assert set(resources) == {"camera", "camera-booking"}
    camera = resources["camera"]
    assert camera["reach"] == "http"
    assert camera["base"] == "$CAMERA_URL"
    assert camera["probe"]["request"] == {"method": "GET", "path": "/health"}
    assert camera["observations"]["recordings"]["request"] == {"method": "GET", "path": "/recordings"}


def test_a_resource_carries_the_name_of_its_secret_and_never_a_value(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAMERA_BOOKING_TOKEN", "s3cret-booking-token")
    write_booking_book(repo)
    booking = book_fixtures.resolved_resources(load(repo))["camera-booking"]
    assert booking["credential"] == {"header": "Authorization", "scheme": "Bearer", "secret": "CAMERA_BOOKING_TOKEN"}
    assert "s3cret-booking-token" not in json.dumps(booking)
