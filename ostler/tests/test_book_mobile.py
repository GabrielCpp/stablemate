"""The device surface of the book runtime, played against a fake adb and a fake Maestro."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from ostler.book import BookError, CannotReach, Device, Environment, MobileSurface, Screen, T
from ostler.book.device import joined, nodes_of
from ostler.book.screen import Button, Field, Text
from ostler.qa import android
from ostler.qa.android import ScreenRecording


def node(bounds: str, **attributes: str) -> dict[str, Any]:
    return {"attributes": {"bounds": bounds, **attributes}, "children": []}


HIERARCHY = json.dumps({"attributes": {}, "children": [
    node("[0,0][1080,2400]", **{"class": "android.view.View"}),
    node("[40,300][1040,420]", **{"class": "android.widget.EditText", "hintText": "Enter your name", "text": "Ana", "resource-id": "field.name"}),
    node("[40,500][1040,620]", **{"class": "android.widget.Button", "accessibilityText": "Save Changes", "enabled": "false"}),
    node("[40,800][1040,900]", **{"class": "android.view.View", "accessibilityText": "Save Changes"}),
    node("[0,0][0,0]", **{"accessibilityText": "Nothing drawn"}),
]})


class Profile(Screen):
    root = Text("form")
    who = Field("field.name", T("Enter your name", "Votre nom"))
    save = Button(None, T("Save Changes", "Enregistrer"))
    ghost = Text(None, T("Nothing drawn", "Rien"))


class Calls:
    def __init__(self) -> None:
        self.argv: list[list[str]] = []
        self.shown = HIERARCHY
        self.keyboard = False

    def run(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.argv.append(argv)
        out = "mInputShown=true" if "dumpsys" in argv and self.keyboard else "device\n" if "get-state" in argv else ""
        return subprocess.CompletedProcess(argv, 0, out, "")

    def reader(self, _timeout: float) -> str:
        return self.shown


class FakeScreen:
    def __init__(self, calls: Calls) -> None:
        self.resident_reader = calls.reader

    def release_device(self) -> None:
        return None


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    calls = Calls()
    monkeypatch.setattr(subprocess, "run", calls.run)
    monkeypatch.setattr("ostler.book.device.load_harness_module", lambda _name: FakeScreen(calls))
    return calls


def page(video_dir: str | None = None) -> Device:
    device = Device("com.example.app", timeout=0.0)
    device.video_dir = video_dir
    return device


def test_nodes_are_the_drawn_elements_with_their_names() -> None:
    found = nodes_of(HIERARCHY)

    assert [(n.id, n.kind, n.box) for n in found[1:3]] == [("field.name", "EditText", (40, 300, 1040, 420)), ("", "Button", (40, 500, 1040, 620))]
    assert found[1].names == ("Enter your name", "Ana") or found[1].names == ("Ana", "Enter your name")
    assert all(n.names != ("Nothing drawn",) for n in found)
    assert found[2].enabled is False and found[1].enabled is True


def test_a_component_is_found_by_its_id_or_by_its_name_and_role(calls: Calls) -> None:
    device = page()

    assert device.locate(Profile.who).centre == (540, 360)
    assert device.locate(Profile.save).box == (40, 500, 1040, 620)
    assert device.disabled(Profile.save) is True


def test_a_component_is_found_inside_the_root_only(calls: Calls) -> None:
    calls.shown = json.dumps({"attributes": {}, "children": [
        node("[0,0][500,500]", **{"resource-id": "form"}),
        node("[0,0][100,100]", **{"accessibilityText": "Save Changes", "class": "android.widget.Button"}),
        node("[0,600][100,700]", **{"accessibilityText": "Save Changes", "class": "android.widget.Button"}),
    ]})

    assert page().locate(Profile.save, Profile.root).box == (0, 0, 100, 100)
    assert page().find(Profile.save, Text("elsewhere")) is None


def test_waiting_for_a_component_that_never_shows_names_it(calls: Calls) -> None:
    with pytest.raises(BookError, match="missing did not appear"):
        page().wait_for(Text("missing"))


def test_pressing_taps_the_centre_of_the_component(calls: Calls) -> None:
    page().press(Profile.who)

    assert ["adb", "shell", "input", "tap", "540", "360"] in calls.argv


def test_filling_replaces_what_the_field_holds_and_types_the_text(calls: Calls) -> None:
    calls.keyboard = True

    page().fill(Profile.who, "Ana")

    assert calls.argv[-4:-1] == [
        ["adb", "shell", "input", "keyevent", "67"],
        ["adb", "shell", "input", "text", "Ana"],
        ["adb", "shell", "dumpsys", "input_method"],
    ]
    assert calls.argv[-1] == ["adb", "shell", "input", "keyevent", "4"]


def test_a_field_that_lost_a_keystroke_is_typed_again_then_reported(calls: Calls) -> None:
    with pytest.raises(BookError, match="kept 'Ana' after being typed 'Bea'"):
        page().fill(Profile.who, "Bea")

    assert [argv[-1] for argv in calls.argv if "text" in argv] == ["Bea"] * 3


def test_a_field_that_caps_what_it_takes_is_unreachable_and_put_back(calls: Calls) -> None:
    with pytest.raises(CannotReach, match="keeps only its first 3 characters of 5 typed"):
        page().fill(Profile.who, "Ana M")

    assert [argv[-1] for argv in calls.argv if "text" in argv] == ["Ana%sM", "Ana%sM", "Ana"]


def test_a_long_text_is_typed_in_chunks_so_the_device_keeps_every_key(calls: Calls) -> None:
    with pytest.raises(BookError):
        page().fill(Profile.who, "x" * 90)

    assert [len(argv[-1]) for argv in calls.argv if "text" in argv][:3] == [40, 40, 10]


def test_a_screen_read_that_fails_to_inspect_is_read_again(calls: Calls) -> None:
    failures = [RuntimeError("maestro mcp reported an error: Failed to inspect UI: null")]
    shown = calls.reader

    def flaky(timeout: float) -> str:
        if failures:
            raise failures.pop()
        return shown(timeout)

    device = page()
    setattr(device._screen, "resident_reader", flaky)

    assert device.value(Profile.who) == "Ana"
    failures.extend([RuntimeError("other")])
    with pytest.raises(RuntimeError, match="other"):
        device.nodes()


def test_the_first_of_several_components_to_show_is_returned(calls: Calls) -> None:
    device = page()
    ghost = Text("never.there", T("Never", "Jamais"))

    assert device.await_first(ghost, Profile.who) is Profile.who
    with pytest.raises(BookError, match="none of never.there appeared"):
        device.await_first(ghost)


def test_a_snackbar_is_heard_by_its_first_words(calls: Calls) -> None:
    device = page()

    assert device.heard(("Save",)) == "Save Changes"
    assert device.heard(("Failed",)) is None
    assert device.await_heard(("Failed",), present=False) is None
    with pytest.raises(BookError, match="nothing starting 'Failed' appeared"):
        device.await_heard(("Failed",))


def test_waiting_for_a_value_names_the_field_that_never_came_to_hold_it(calls: Calls) -> None:
    device = page()

    device.await_value(Profile.who, "Ana")
    with pytest.raises(BookError, match="field.name did not come to hold 'Bea'"):
        device.await_value(Profile.who, "Bea")


def test_a_text_the_keyboard_cannot_type_is_unreachable(calls: Calls) -> None:
    with pytest.raises(CannotReach, match="cannot be typed"):
        page().fill(Profile.who, "Zoé")

    assert not any("text" in argv for argv in calls.argv)


def test_a_device_is_driven_through_the_serial_it_was_given(calls: Calls) -> None:
    device = Device("com.example.app", serial="emulator-5580")

    device.clear()

    assert calls.argv == [["adb", "-s", "emulator-5580", "shell", "pm", "clear", "com.example.app"]]


def test_a_screen_in_the_wrong_language_is_reported(calls: Calls) -> None:
    wrong = page().wrong_labels("fr", (Profile,))

    assert wrong is not None and "Votre nom" in wrong


def test_the_segments_of_a_recording_are_pulled_in_order(calls: Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(android.time, "sleep", lambda _s: None)
    clock = iter(range(0, 1000, 100))

    class Recorder:
        def poll(self) -> int | None:
            return 0 if any("pkill" in a for a in calls.argv) else None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def pulled(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.argv.append(argv)
        if "pull" in argv:
            Path(argv[-1]).write_bytes(b"mp4")
        if "pgrep" in argv:
            return subprocess.CompletedProcess(argv, 1)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", pulled)
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_k: calls.argv.append(argv) or Recorder())
    recording = ScreenRecording(tmp_path, "journey", "7", lambda: next(clock), "emulator-5580")

    recording.start()
    recording.stop_event.set()
    assert recording.thread is not None
    recording.thread.join(timeout=5)

    assert recording.error == ""
    assert [path.name for path, _start, _end in recording.segments] == ["journey-001.mp4"]
    assert ["adb", "-s", "emulator-5580", "shell", "screenrecord", "--time-limit", "170", "/sdcard/ostler-7-001.mp4"] in calls.argv


def test_a_finished_recording_is_kept_or_deleted(calls: Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Done(ScreenRecording):
        def start(self) -> None:
            clip = tmp_path / "clip-001.mp4"
            clip.write_bytes(b"mp4")
            self.segments.append((clip, 0, 10))
            self.thread = threading.Thread(target=int)
            self.thread.start()

    monkeypatch.setattr("ostler.book.device.ScreenRecording", Done)
    device = page(str(tmp_path))

    assert device.offset() is None
    device.begin("a journey")
    assert device.offset() is not None
    assert device.finish(keep=False) == ""
    assert not (tmp_path / "clip-001.mp4").exists()
    device.begin("a journey")
    kept = device.finish(keep=True)

    assert kept == str(tmp_path / "a-journey.mp4")
    assert device.offset() is None


def test_segments_are_joined_by_ffmpeg_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.mp4").write_bytes(b"1")
    (tmp_path / "b.mp4").write_bytes(b"2")
    seen: list[str] = []

    def ffmpeg(argv: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        seen.append(Path(argv[argv.index("-i") + 1]).read_text())
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", ffmpeg)

    joined([tmp_path / "a.mp4", tmp_path / "b.mp4"], str(tmp_path / "out.mp4"))

    assert seen == [f"file {tmp_path}/a.mp4\nfile {tmp_path}/b.mp4\n"]
    joined([tmp_path / "a.mp4"], str(tmp_path / "one.mp4"))
    assert (tmp_path / "one.mp4").read_bytes() == b"1"


def test_a_mobile_surface_records_through_its_device(calls: Calls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScreenRecording, "start", lambda self: None)
    class App(MobileSurface):
        app_id = "com.example.app"

        def __init__(self) -> None:
            super().__init__(Environment("local", {}), (Profile,))
            self.opened = 0

        def open(self) -> None:
            self.opened += 1

        def restore(self) -> None:
            return None

    surface = App()
    surface.record_to(str(tmp_path))
    surface.record("first")

    assert isinstance(surface.browser, Device)
    assert surface.browser.video_dir == str(tmp_path)
    assert surface.strays() == []
    assert surface.opened == 1
    surface.reset()
    assert surface.opened == 2


def test_a_field_showing_only_its_hint_holds_nothing() -> None:
    raw = json.dumps({"attributes": {}, "children": [
        node("[40,300][1040,420]", **{"class": "android.widget.EditText", "hintText": "Enter your name", "text": "Enter your name", "resource-id": "field.name"}),
    ]})

    assert [found.text for found in nodes_of(raw)] == [""]
