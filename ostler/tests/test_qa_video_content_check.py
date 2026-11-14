"""A frozen video is not the same observation as a blank one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-video-1", "story-1", {})
    return PythonDriver(
        session, "web", {"driver": "playwright"}, root=repo, variables={}
    )


def _video_record(repo: Path) -> dict:
    video = repo / "docs/specs/story-1/qa/artifacts/run.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"\x00")
    return {"type": "artifact", "path": str(video), "kind": "video"}


def _asserts(driver: PythonDriver) -> list[dict]:
    log = driver.session.qa_dir / "qa-run.ndjson"
    if not log.is_file():
        return []
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [entry for entry in entries if entry.get("kind") == "assert"]


def _stub_measurement(monkeypatch: pytest.MonkeyPatch, *, static: bool) -> None:
    monkeypatch.setattr(
        "ostler.qa.drivers._probe_media",
        lambda path: {"width": 1440, "height": 900, "durationSeconds": 3.0},
    )
    monkeypatch.setattr("ostler.qa.drivers._is_static", lambda path, duration: static)


def test_a_genuinely_blank_recording_is_still_flagged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No vet corroborates content, so the freeze verdict stands."""
    _stub_measurement(monkeypatch, static=True)
    driver = _driver(repo)
    records = [
        _video_record(repo),
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]

    result = driver._grade("s-1", [], records, "", 0, timed_out=False)

    assert "painted nothing" in result.message
    assert result.aborted

