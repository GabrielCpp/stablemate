"""A frozen video is not the same observation as a blank one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession

from conftest import write

SCREEN = "docs/features/groom/gui/screens/s.md"


def _book(repo: Path) -> None:
    write(
        repo / SCREEN,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
        "## Components\n\n"
        "### body\n- role: article\n- selector: `article.prose`\n"
        "- placement: width 60-100%\n",
    )


def _shot(repo: Path, regions: list[dict]) -> Path:
    shot = repo / "docs/specs/story-1/qa/artifacts/loaded.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG")
    shot.with_suffix(".layout.json").write_text(
        json.dumps({"viewport": {"width": 1440, "height": 900}}), encoding="utf-8"
    )
    shot.with_suffix(".regions.json").write_text(json.dumps(regions), encoding="utf-8")
    return shot


def _region(role: str, selector: str, box: tuple[float, float, float, float]) -> dict:
    x, y, width, height = box
    return {
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "role": role,
        "selectors": [selector],
    }


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8"
    )
    session = QaSession.create(spec, "qa-video-1", "story-1", {})
    return PythonDriver(
        session, "web", {"driver": "playwright"}, root=repo, variables={}
    )


def _video_record(repo: Path) -> dict:
    video = repo / "docs/specs/story-1/qa/artifacts/run.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"\x00")
    return {"type": "artifact", "path": str(video), "kind": "video"}


def _vet_record(shot: Path) -> dict:
    return {
        "type": "vet",
        "screen": SCREEN,
        "state": "loaded",
        "screenshot": str(shot),
        "regions": str(shot.with_suffix(".regions.json")),
        "components": [],
    }


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


def test_a_still_but_rendered_page_is_not_reported_as_blank(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression: a scenario whose page painted, but never moved, used to abort."""
    _book(repo)
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 1400, 760))])
    _stub_measurement(monkeypatch, static=True)
    driver = _driver(repo)
    records = [
        _vet_record(shot),
        _video_record(repo),
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]

    result = driver._grade("s-1", [], records, "", 0, timed_out=False)

    assert "painted nothing" not in result.message
    assert not result.aborted


def test_a_genuinely_blank_recording_is_still_flagged(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No vet corroborates content, so the freeze verdict stands."""
    _book(repo)
    _stub_measurement(monkeypatch, static=True)
    driver = _driver(repo)
    records = [
        _video_record(repo),
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]

    result = driver._grade("s-1", [], records, "", 0, timed_out=False)

    assert "painted nothing" in result.message
    assert result.aborted


def test_a_vet_with_only_zero_area_regions_does_not_corroborate(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A region with no extent is not evidence the page drew anything."""
    _book(repo)
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 0, 0))])
    _stub_measurement(monkeypatch, static=True)
    driver = _driver(repo)
    records = [
        _vet_record(shot),
        _video_record(repo),
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]

    result = driver._grade("s-1", [], records, "", 0, timed_out=False)

    assert "painted nothing" in result.message
