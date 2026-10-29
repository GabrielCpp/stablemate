"""The `resource` node type, a step's `request:` and a claim's `observe:`: the grammar registers, and each doctor code fires on the smallest page that breaks it."""

from __future__ import annotations

from pathlib import Path

import pytest

from booking_fake import CAMERA_BOOKED_PAGE, CAMERA_BOOKING_PAGE, CAMERA_PAGE, SERVER_PAGE, write_booking_book
from ostler import doctor, registry
from ostler.model import load

from conftest import write

BASE = "docs/services/lab"

CODES = (
    "resource-reach-shape", "resource-probe-shape", "resource-observation-shape", "step-request-shape",
    "step-reach-mismatch", "fixture-borrow-lifetime", "fixture-release-without-borrow", "fixture-probe-local",
    "unknown-observation", "unparsed-observation", "within-off-observation",
)


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def _break(repo: Path, relative: str, old: str, new: str, original: str) -> None:
    assert old in original
    write(repo / BASE / relative, original.replace(old, new))


def test_resource_is_a_file_type_with_probe_and_observation_containers() -> None:
    uitype = registry.UI_TYPES_BY_NAME["resource"]
    assert uitype.kind == "file"
    assert {b.key for b in uitype.bullet_keys} >= {"reach", "base", "credential"}


def test_observe_is_declared_on_the_claim_types() -> None:
    for node_type in ("environment", "command", "endpoint", "interaction", "invocation", "method", "field"):
        assert "observe" in {b.key for b in registry.UI_TYPES_BY_NAME[node_type].bullet_keys}, node_type


def test_the_valid_booking_book_raises_none_of_the_resource_codes(repo: Path) -> None:
    write_booking_book(repo)
    assert not _codes(repo) & set(CODES)


@pytest.mark.parametrize(
    ("code", "relative", "old", "new", "original"),
    [
        ("resource-reach-shape", "resources/camera.md", "- reach: http", "- reach: carrier-pigeon", CAMERA_PAGE),
        ("resource-reach-shape", "resources/camera.md", "- base: $CAMERA_URL\n", "", CAMERA_PAGE),
        ("resource-reach-shape", "resources/camera-booking.md", "  - secret: CAMERA_BOOKING_TOKEN",
         "  - secret: not a name", CAMERA_BOOKING_PAGE),
        ("resource-probe-shape", "resources/camera.md", "- kind: probe", "- kind: observe", CAMERA_PAGE),
        ("resource-observation-shape", "resources/camera.md", "- kind: observe", "- kind: probe", CAMERA_PAGE),
        ("resource-observation-shape", "resources/camera.md", "- request: GET /recordings",
         "- request: POST /recordings", CAMERA_PAGE),
        ("step-request-shape", "fixtures/camera-booked.md", "- request: POST /leases", "- request: FETCH /leases",
         CAMERA_BOOKED_PAGE),
        ("step-request-shape", "fixtures/camera-booked.md", '- body: {"device": "camera-1"}', "- body: not json",
         CAMERA_BOOKED_PAGE),
        ("step-reach-mismatch", "resources/camera-booking.md", "- reach: http", "- reach: cli", CAMERA_BOOKING_PAGE),
        ("fixture-borrow-lifetime", "fixtures/camera-booked.md", "- lifetime: scenario", "- lifetime: run",
         CAMERA_BOOKED_PAGE),
        ("fixture-release-without-borrow", "fixtures/camera-booked.md", "- kind: borrow", "- kind: seed",
         CAMERA_BOOKED_PAGE),
        ("fixture-probe-local", "resources/camera.md", "- base: $CAMERA_URL", "- base: http://localhost:8080",
         CAMERA_PAGE),
        ("unknown-observation", "server.md", "@camera.recordings", "@camera.nothing", SERVER_PAGE),
        ("unknown-observation", "server.md", "@camera.recordings", "@nowhere.recordings", SERVER_PAGE),
        ("unparsed-observation", "server.md", "@camera.recordings", "the camera recordings", SERVER_PAGE),
        ("within-off-observation", "server.md", "- verify: json_path(path=\"$.accepted\", equals=true)",
         "- verify: json_path(path=\"$.accepted\", equals=true, within=5)", SERVER_PAGE),
    ],
)
def test_each_resource_code_fires_on_the_smallest_page_that_breaks_it(
    repo: Path, code: str, relative: str, old: str, new: str, original: str,
) -> None:
    write_booking_book(repo)
    _break(repo, relative, old, new, original)
    assert code in _codes(repo)
