"""Each vet keeps the photograph it took: the grader reads a vet's regions by path after the scenario ends, so two vets sharing one path would both be judged on the last screen."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
hierarchy = load_harness_module("ostler_qa_hierarchy")

LOGIN = "docs/features/app/gui/screens/login.md"
ONBOARDING = "docs/features/app/gui/screens/onboarding.md"


def _element(selector: str) -> dict[str, Any]:
    return {
        "selector": selector,
        "tag": "android.widget.Button",
        "role": "button",
        "name": selector,
        "bbox": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 40.0},
    }


def _device_qa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, screens: list[list[str]]) -> tuple[Any, list[dict[str, Any]]]:
    remaining = list(screens)

    def scan(*, source: str = "maestro", udid: str = "") -> tuple[dict[str, Any], list[dict[str, Any]]]:
        selectors = remaining.pop(0)
        frame = {"viewport": {"width": 1080.0, "height": 2400.0}, "document": {"width": 1080.0, "height": 2400.0}}
        return frame, [_element(selector) for selector in selectors]

    def screenshot(path: Path, *, udid: str = "", timeout: float = 120.0) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG")
        return path

    monkeypatch.setattr(hierarchy, "scan", scan)
    monkeypatch.setattr(hierarchy, "screenshot", screenshot)
    emitted: list[dict[str, Any]] = []
    recorder = harness._Recorder(fd=-1)
    recorder.emit = emitted.append
    qa = harness.Qa(
        scenario_id="login-from-the-book",
        target=harness.Target("app_mobile", driver="maestro", app_id="com.example.app"),
        root=tmp_path,
        spec_dir=tmp_path,
        qa_dir=tmp_path / "qa",
        covers=["ac:1"],
        recorder=recorder,
    )
    return qa, emitted


def _selectors(regions_path: str) -> list[str]:
    regions = json.loads(Path(regions_path).read_text(encoding="utf-8"))
    return sorted(selector for region in regions for selector in region["selectors"])


def test_each_vet_keeps_its_own_photograph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scenario vets the login screen, taps through to onboarding and vets again; the login vet's regions still name the login buttons once the scenario is over."""
    qa, emitted = _device_qa(tmp_path, monkeypatch, [["action.sign-in.google"], ["action.skip-onboarding"]])

    qa.vet(LOGIN)
    qa.vet(ONBOARDING)

    vets = [record for record in emitted if record["type"] == "vet"]
    assert [vet["screen"] for vet in vets] == [LOGIN, ONBOARDING]
    assert vets[0]["regions"] != vets[1]["regions"]
    assert _selectors(vets[0]["regions"]) == ["action.sign-in.google"]
    assert _selectors(vets[1]["regions"]) == ["action.skip-onboarding"]
    assert all(Path(vet["screenshot"]).is_file() for vet in vets)


def test_two_vets_of_one_named_state_keep_both_photographs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A state walk settles the same state twice; the two readings stay distinct and the record still names the state."""
    qa, emitted = _device_qa(tmp_path, monkeypatch, [["a"], ["b"]])

    qa.vet(LOGIN, name="signed-out")
    qa.vet(LOGIN, name="signed-out")

    vets = [record for record in emitted if record["type"] == "vet"]
    assert [vet["state"] for vet in vets] == ["signed-out", "signed-out"]
    assert _selectors(vets[0]["regions"]) == ["a"]
    assert _selectors(vets[1]["regions"]) == ["b"]
