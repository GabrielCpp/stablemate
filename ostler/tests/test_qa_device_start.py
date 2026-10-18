from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.qa.drivers import DriverBlocked, PythonDriver
from ostler.qa.session import QaSession

APP_ID = "com.example.acme"


def _fake_tool(directory: Path, name: str, script: str) -> None:
    tool = directory / name
    tool.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    tool.chmod(0o755)


def _device_driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
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
