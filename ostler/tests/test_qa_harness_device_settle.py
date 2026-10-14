"""A device screen settling: the busy sign goes and the state that holds is the one a flow names, read from the view hierarchy."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
settle = load_harness_module("ostler_qa_settle")
hierarchy = load_harness_module("ostler_qa_hierarchy")

CEILING_S = 0.3

NODE = "gui/screens/results.md#loaded"

STATES = {
    "loaded": [{"role": "table", "name": "Results"}, {"role": "alert", "name": "Could not load results", "absent": True}],
    "error": [{"role": "alert", "name": "Could not load results"}],
}

BUSY = {"role": "progressbar", "name": "Loading results"}


def _document(*nodes: dict) -> str:
    drawn = [{"attributes": {"bounds": "[0,0][100,100]", **attributes}, "children": []} for attributes in nodes]
    return "Running on emulator-5554\n" + json.dumps({"attributes": {}, "children": drawn})


BUSY_SCREEN = _document({"class": "android.widget.ProgressBar", "content-desc": "Loading results"})
LOADED_SCREEN = _document({"class": "android.widget.TableLayout", "content-desc": "Results"})
ERROR_SCREEN = _document({"class": "android.widget.TextView", "text": "Could not load results"})


def _reader(*documents: str) -> Callable[[float], str]:
    remaining = list(documents)

    def read(timeout: float) -> str:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return read


def _settle(reader: Callable[[float], str]) -> Any:
    return settle.settle_screen(
        hierarchy.DeviceScreen(reader), None, NODE,
        since=0, requests=[], busy=BUSY, states=STATES, expect="loaded", ceiling_s=CEILING_S,
    )


def test_a_screen_that_stops_being_busy_and_shows_the_table_settles_on_the_named_state() -> None:
    settled = _settle(_reader(BUSY_SCREEN, BUSY_SCREEN, LOADED_SCREEN))

    assert settled.passed
    assert settled.held == "loaded"


def test_a_screen_that_ends_on_the_error_fails_at_once_naming_the_state() -> None:
    settled = _settle(_reader(BUSY_SCREEN, ERROR_SCREEN))

    assert not settled.passed
    assert settled.held == "error"
    assert "expected state 'loaded', screen shows 'error'" in settled.message


def test_a_screen_that_stays_busy_fails_at_the_ceiling_naming_the_busy_sign() -> None:
    settled = _settle(_reader(BUSY_SCREEN))

    assert not settled.passed
    assert "busy sign still shown: progressbar 'Loading results'" in settled.message
    assert f"{CEILING_S:g}s" in settled.message


def test_a_screen_that_cannot_be_read_fails_at_the_ceiling_saying_so() -> None:
    def unreadable(timeout: float) -> str:
        raise subprocess.TimeoutExpired("maestro hierarchy", timeout)

    settled = _settle(unreadable)

    assert not settled.passed
    assert "the screen could not be read" in settled.message


def test_a_screen_that_shows_no_declared_state_fails_at_the_ceiling() -> None:
    settled = _settle(_reader(_document({"class": "android.widget.TextView", "text": "Welcome"})))

    assert not settled.passed
    assert "no declared state holds: loaded, error" in settled.message


class _Device:
    scenario_id = "device"
    target = SimpleNamespace(name="mobile", driver="maestro")
    ceiling_s = CEILING_S


def test_settling_a_device_with_requests_to_wait_for_is_refused() -> None:
    with pytest.raises(ValueError, match="a device has no request feed"):
        harness.Qa.settle(
            _Device(), NODE, requests=[("GET", "/api/results")], busy=BUSY, states=STATES, expect="loaded",
        )


class _Recorded:
    def __init__(self, directory: Path) -> None:
        self.scenario_id = "flow"
        self.dir = directory
        self.root = directory
        self.artifacts: list[Path] = []

    def artifact(self, path: Path, *, kind: str) -> None:
        self.artifacts.append(path)


def test_a_required_flow_that_exits_non_zero_raises_after_its_artifacts_are_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    qa = _Recorded(tmp_path)
    flow = tmp_path / "walk-1.yaml"
    flow.write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    monkeypatch.setattr(harness.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        harness.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "Element not found: Open details\n"),
    )

    with pytest.raises(RuntimeError, match=r"walk-1\.yaml exited 1[\s\S]*Element not found: Open details"):
        harness.Maestro(qa).run(flow, require=True)

    assert qa.artifacts


def test_a_flow_that_is_not_required_hands_back_its_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    flow = tmp_path / "walk-2.yaml"
    flow.write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    monkeypatch.setattr(harness.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        harness.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", ""),
    )

    assert harness.Maestro(_Recorded(tmp_path)).run(flow).exit_code == 1


def test_settling_a_device_with_origins_to_watch_is_refused() -> None:
    with pytest.raises(ValueError, match="a device has no request feed"):
        harness.Qa.settle(
            _Device(), NODE, busy=BUSY, states=STATES, expect="loaded", origins=["http://127.0.0.1:8099"],
        )
