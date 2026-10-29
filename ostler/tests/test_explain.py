"""`ostler explain <resource>`: the page, its probe and observations, who borrows it and which claims depend on it."""

from __future__ import annotations

from pathlib import Path

import pytest

from booking_fake import write_booking_book
from ostler.cli import main


def _explain(repo: Path, name: str) -> int:
    return main(["-C", str(repo), "explain", name])


def test_explain_prints_the_five_sections_in_order(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_booking_book(repo)
    assert _explain(repo, "camera-booking") == 0
    out = capsys.readouterr().out
    marks = ["type: resource", "probe: GET /health on $BOOKING_URL", "## Observations\n\nleases: GET /leases",
             "## Borrowed by\n\ncamera-booked: borrow take, release give-back", "## Claims\n\nfixture camera-booked:"]
    positions = [out.index(mark) for mark in marks]
    assert positions == sorted(positions)
    assert "docs/services/lab/server.md#play" in out


def test_explain_names_the_claims_that_observe_a_resource(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_booking_book(repo)
    assert _explain(repo, "camera") == 0
    out = capsys.readouterr().out
    assert "no fixture borrows from it" in out
    assert "observe @camera.recordings:\n  docs/services/lab/server.md#play" in out


def test_an_unknown_resource_exits_one_and_says_how_to_look(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_booking_book(repo)
    assert _explain(repo, "nowhere") == 1
    assert "no resource named 'nowhere'" in capsys.readouterr().err
