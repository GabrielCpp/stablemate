from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from ostler.qa import drivers
from ostler.qa.drivers import DeviceRecorder, DriverBlocked, PythonDriver
from ostler.qa.session import QaSession

APP_ID = "com.example.acme"


def _fake_tool(directory: Path, name: str, script: str) -> None:
    tool = directory / name
    tool.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    tool.chmod(0o755)


def _device_driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"servicesRoot": "docs/services"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-device-start-1", "story-1", {})
    target = {"driver": "maestro", "device": "android", "app_id": APP_ID, "recording": {"required": False}}
    return PythonDriver(session, "acme", target, root=repo, variables={})


def _adb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, state: str, packages: str) -> None:
    _fake_tool(tmp_path, "maestro", "exit 0")
    _fake_tool(
        tmp_path,
        "adb",
        f'case "$1" in\n'
        f'  get-state) echo "{state}"; [ "{state}" = device ] || exit 1 ;;\n'
        f'  shell) [ -n "{packages}" ] && echo "{packages}" || exit 1 ;;\n'
        f'esac',
    )
    monkeypatch.setenv("PATH", str(tmp_path))


def test_a_device_start_says_no_android_device_is_attached_before_probing_the_app(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adb(tmp_path, monkeypatch, state="error: no devices/emulators found", packages=f"package:/data/{APP_ID}.apk")

    with pytest.raises(DriverBlocked) as blocked:
        _device_driver(repo)._start_device({"required": False})

    assert "no Android device is attached" in str(blocked.value)
    assert "kind: prepare" in str(blocked.value)
    assert APP_ID not in str(blocked.value)


def test_a_device_start_names_the_bundle_id_when_the_attached_device_lacks_the_app(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adb(tmp_path, monkeypatch, state="device", packages="")

    with pytest.raises(DriverBlocked) as blocked:
        _device_driver(repo)._start_device({"required": False})

    assert f"app {APP_ID} is not installed" in str(blocked.value)
    assert "kind: prepare" in str(blocked.value)
    assert "adb install" in str(blocked.value)
    assert "no Android device" not in str(blocked.value)


def test_a_device_start_passes_when_the_device_holds_the_app(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adb(tmp_path, monkeypatch, state="device", packages=f"package:/data/{APP_ID}.apk")
    driver = _device_driver(repo)

    driver._start_device({"required": False})

    assert driver._device_recorder is None


class _FakeScreenrecord:
    def __init__(self, device: "_FakeDevice") -> None:
        self.device = device

    def poll(self) -> int | None:
        return self.device.client_exit

    def send_signal(self, _signal: int) -> None:
        self.device.client_exit = 0

    def wait(self, timeout: float | None = None) -> int:
        if self.device.client_exit is None:
            raise subprocess.TimeoutExpired("adb", timeout or 0)
        return self.device.client_exit

    def kill(self) -> None:
        self.device.client_exit = -9


class _FakeDevice:
    def __init__(self) -> None:
        self.client_exit: int | None = None
        self.finalized = False
        self.finalize_polls_left = 2
        self.events: list[str] = []

    def popen(self, argv: list[str], **_kwargs: object) -> _FakeScreenrecord:
        self.events.append("record")
        return _FakeScreenrecord(self)

    def run(self, argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if argv[:5] == ["adb", "shell", "pkill", "-INT", "-f"]:
            self.events.append("pkill")
            self.client_exit = 0
            return subprocess.CompletedProcess(argv, 0)
        if argv[:4] == ["adb", "shell", "pgrep", "-f"]:
            self.events.append("pgrep")
            if "pkill" not in self.events:
                return subprocess.CompletedProcess(argv, 0)
            self.finalize_polls_left -= 1
            self.finalized = self.finalize_polls_left < 0
            return subprocess.CompletedProcess(argv, 1 if self.finalized else 0)
        if argv[:2] == ["adb", "pull"]:
            self.events.append("pull-finalized" if self.finalized else "pull-truncated")
            Path(argv[3]).write_bytes(b"mp4")
            return subprocess.CompletedProcess(argv, 0)
        return subprocess.CompletedProcess(argv, 0)


def test_stopping_an_android_recording_pulls_the_video_only_after_the_phone_finalized_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _FakeDevice()
    monkeypatch.setattr(drivers.subprocess, "Popen", device.popen)
    monkeypatch.setattr(drivers.subprocess, "run", device.run)
    monkeypatch.setattr(drivers.time, "sleep", lambda _seconds: None)
    session = _device_driver(repo).session
    recorder = DeviceRecorder(session, "acme", {"device": "android"})
    recorder.path.parent.mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=recorder._android_loop)

    thread.start()
    recorder._started_event.wait(timeout=5)
    recorder._stop_event.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert recorder._thread_error == ""
    assert "pkill" in device.events
    assert device.events.index("pkill") < device.events.index("pull-finalized")
    assert "pull-truncated" not in device.events
