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


def _reader_then_unreadable(document: str) -> Callable[[float], str]:
    documents = [document]

    def read(timeout: float) -> str:
        if documents:
            return documents.pop()
        raise subprocess.TimeoutExpired("maestro hierarchy", timeout)

    return read


def test_a_screen_read_once_and_then_cut_off_by_the_ceiling_fails_on_what_that_reading_showed() -> None:
    settled = _settle(_reader_then_unreadable(_document({"class": "android.widget.TextView", "text": "Welcome"})))

    assert not settled.passed
    assert "no declared state holds: loaded, error" in settled.message
    assert "could not be read" not in settled.message


def test_a_busy_screen_read_once_and_then_cut_off_by_the_ceiling_names_the_busy_sign() -> None:
    settled = _settle(_reader_then_unreadable(BUSY_SCREEN))

    assert not settled.passed
    assert "busy sign still shown: progressbar 'Loading results'" in settled.message


def test_a_screen_that_shows_no_declared_state_fails_at_the_ceiling() -> None:
    settled = _settle(_reader(_document({"class": "android.widget.TextView", "text": "Welcome"})))

    assert not settled.passed
    assert "no declared state holds: loaded, error" in settled.message


def test_a_settle_that_times_out_on_no_declared_state_lists_what_the_screen_showed() -> None:
    settled = _settle(_reader(_document({"class": "android.widget.TextView", "text": "Welcome"})))

    assert settled.message.endswith("; the screen shows: element 'Welcome'")


def test_a_settle_that_times_out_on_the_busy_sign_lists_what_the_screen_showed() -> None:
    settled = _settle(_reader(BUSY_SCREEN))

    assert settled.message.endswith("; the screen shows: progressbar 'Loading results'")


class _Page:
    def __init__(self, snapshot: str | Exception) -> None:
        self._snapshot = snapshot

    def locator(self, selector: str) -> "_Page":
        return self

    def aria_snapshot(self) -> str:
        if isinstance(self._snapshot, Exception):
            raise self._snapshot
        return self._snapshot


def test_a_page_inventory_is_its_aria_snapshot_collapsed_and_clipped() -> None:
    reading = settle.PageReading(_Page("- main:\n  - button \"Save\"\n" + "x" * 2000))

    assert reading.inventory().startswith('- main: - button "Save" xxx')
    assert len(reading.inventory()) == 1500


def test_a_page_that_cannot_snapshot_has_an_empty_inventory() -> None:
    assert settle.PageReading(_Page(RuntimeError("closed"))).inventory() == ""


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


class _Look:
    def __init__(self, inventory: str | Exception) -> None:
        self.reads = 0
        self._inventory = inventory

    def read(self, within: float) -> Any:
        self.reads += 1
        if isinstance(self._inventory, Exception):
            raise self._inventory
        inventory = self._inventory
        return SimpleNamespace(inventory=lambda: inventory)


def _stub_maestro(monkeypatch: pytest.MonkeyPatch, look: _Look, code: int, junit: str = "") -> None:
    monkeypatch.setattr(harness.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(harness, "_harness_module", lambda name: SimpleNamespace(DeviceScreen=lambda: look))

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if junit:
            Path(command[command.index("--output") + 1]).write_text(junit, encoding="utf-8")
        return subprocess.CompletedProcess(command, code, "step one\nAssertion failed\n", "")

    monkeypatch.setattr(harness.subprocess, "run", run)


JUNIT = (
    '<testsuites><testsuite><testcase name="walk"><failure message="Element not found: Open details"/>'
    "</testcase></testsuite></testsuites>"
)


def _flow(tmp_path: Path) -> Path:
    flow = tmp_path / "walk-3.yaml"
    flow.write_text("appId: x\n---\n- launchApp\n", encoding="utf-8")
    return flow


def test_a_failed_flow_reports_the_failing_step_and_what_the_screen_showed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _stub_maestro(monkeypatch, _Look("button 'Save'"), 1, JUNIT)

    result = harness.Maestro(_Recorded(tmp_path)).run(_flow(tmp_path))

    assert result.seen == (
        "maestro stopped at: Element not found: Open details. The screen showed: button 'Save'"
    )


def test_a_failed_flow_without_a_junit_failure_names_the_last_line_of_its_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _stub_maestro(monkeypatch, _Look(""), 1)

    result = harness.Maestro(_Recorded(tmp_path)).run(_flow(tmp_path))

    assert result.seen == "maestro stopped at: Assertion failed"


def test_a_passing_flow_never_reads_the_screen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    look = _Look("button 'Save'")
    _stub_maestro(monkeypatch, look, 0)

    result = harness.Maestro(_Recorded(tmp_path)).run(_flow(tmp_path))

    assert (look.reads, result.seen) == (0, "")


def test_a_required_flow_that_fails_carries_what_the_screen_showed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _stub_maestro(monkeypatch, _Look("button 'Save'"), 1, JUNIT)

    with pytest.raises(RuntimeError, match=r"The screen showed: button 'Save'$"):
        harness.Maestro(_Recorded(tmp_path)).run(_flow(tmp_path), require=True)


def test_a_screen_that_cannot_be_read_never_replaces_the_flows_own_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _stub_maestro(monkeypatch, _Look(OSError("no device")), 1, JUNIT)

    result = harness.Maestro(_Recorded(tmp_path)).run(_flow(tmp_path))

    assert result.exit_code == 1
    assert result.seen == "maestro stopped at: Element not found: Open details. The screen could not be read: OSError"


def _verifying(tmp_path: Path, emitted: list[dict[str, Any]]) -> Any:
    recorder = harness._Recorder(fd=-1)
    recorder.emit = emitted.append
    return harness.Qa(
        scenario_id="phone-check", target=harness.Target("phone", driver="maestro"), root=tmp_path,
        spec_dir=tmp_path, qa_dir=tmp_path / "qa", covers=["ac:1"], recorder=recorder,
    )


def test_a_failed_phone_check_records_what_the_screen_showed(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _verifying(tmp_path, emitted)
    failed = harness.MaestroResult(exit_code=1, output="", flow=tmp_path / "f.yaml", seen="maestro stopped at: x")
    passed = harness.MaestroResult(exit_code=0, output="", flow=tmp_path / "f.yaml", seen="ignored")

    qa.verify("visible", failed)
    qa.verify("visible", passed)

    assert [record.get("seen") for record in emitted] == ["maestro stopped at: x", None]
