"""Typing a stored secret into the focused field of an Android device, over adb."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree

TIMEOUT_SECONDS = 30.0

DUMP_ATTEMPTS = 5

DUMP_PAUSE_SECONDS = 1.0

SERVER_HOST = "127.0.0.1"

SERVER_ENV = ("ADB_SERVER_SOCKET", "ANDROID_ADB_SERVER_ADDRESS", "ADB_TRACE")

EDITABLE_CLASSES = ("EditText", "AutoCompleteTextView")

REMOTE_MARKS = (":", "_adb-tls-connect")

READY = "device"


class DeviceError(RuntimeError):
    """The device could not be reached, or could not be made to accept the value."""


@dataclass(frozen=True)
class FocusedField:
    """The field that has input focus. Its length is kept and its text never is."""

    package: str
    resource_id: str
    is_password: bool
    length: int


class DeviceSession(Protocol):
    """One device's screen and keyboard."""

    def screen(self) -> str: ...

    def type_text(self, value: str) -> None: ...


def find_adb(env: Mapping[str, str] | None = None) -> str:
    environ = os.environ if env is None else env
    found = shutil.which("adb", path=environ.get("PATH"))
    if found:
        return found
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = environ.get(key)
        if root and (Path(root) / "platform-tools" / "adb").is_file():
            return str(Path(root) / "platform-tools" / "adb")
    raise DeviceError("adb was not found. Put the Android platform-tools on PATH or set ANDROID_HOME where saddlebag runs.")


def _adb(adb: str, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in SERVER_ENV}
    try:
        return subprocess.run(
            [adb, "-H", SERVER_HOST, *args],
            input=stdin,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceError(f"adb {args[-1]} did not finish: {type(exc).__name__}") from None


def list_devices(adb: str) -> dict[str, str]:
    done = _adb(adb, "devices")
    if done.returncode != 0:
        raise DeviceError("adb could not list the devices. Is its server running on this machine?")
    pairs = (line.split() for line in done.stdout.splitlines()[1:])
    return {pair[0]: pair[1] for pair in pairs if len(pair) >= 2}


def select_serial(devices: Mapping[str, str], wanted: str | None) -> str:
    listed = ", ".join(f"{serial} ({state})" for serial, state in sorted(devices.items())) or "none"
    if wanted is None:
        ready = sorted(serial for serial, state in devices.items() if state == READY)
        if not ready:
            raise DeviceError(f"no device is ready. Attached: {listed}")
        if len(ready) > 1:
            raise DeviceError(f"{len(ready)} devices are ready. Pick one with --device. Attached: {listed}")
        wanted = ready[0]
    elif devices.get(wanted) != READY:
        raise DeviceError(f"{wanted} is not a ready device. Attached: {listed}")
    if any(mark in wanted for mark in REMOTE_MARKS):
        raise DeviceError(f"{wanted} is attached over the network. saddlebag types only to USB devices and emulators.")
    return wanted


class AdbSession:
    """A :class:`DeviceSession` over the adb server on this machine."""

    def __init__(self, adb: str, serial: str) -> None:
        self.adb = adb
        self.serial = serial

    def screen(self) -> str:
        for attempt in range(DUMP_ATTEMPTS):
            if attempt:
                time.sleep(DUMP_PAUSE_SECONDS)
            output = _adb(self.adb, "-s", self.serial, "exec-out", "uiautomator", "dump", "/dev/tty").stdout
            start, end = output.find("<hierarchy"), output.rfind("</hierarchy>")
            if start != -1 and end != -1:
                return output[start : end + len("</hierarchy>")]
        raise DeviceError(f"{self.serial} did not return its screen after {DUMP_ATTEMPTS} tries. Check that it is awake and unlocked.")

    def type_text(self, value: str) -> None:
        done = _adb(self.adb, "-s", self.serial, "shell", stdin=f"input text {shlex.quote(value)}\n")
        if done.returncode != 0:
            raise DeviceError(f"{self.serial} refused the input command. Check the field before you retry, it may hold part of the value.")


def connect(serial: str | None) -> AdbSession:
    adb = find_adb()
    return AdbSession(adb, select_serial(list_devices(adb), serial))


def focused_field(screen: str) -> FocusedField | None:
    try:
        root = ElementTree.fromstring(screen)
    except ElementTree.ParseError:
        raise DeviceError("the device returned a screen that could not be parsed") from None
    for node in root.iter("node"):
        if node.get("focused") == "true" and node.get("class", "").endswith(EDITABLE_CLASSES):
            return FocusedField(
                package=node.get("package", ""),
                resource_id=node.get("resource-id", ""),
                is_password=node.get("password") == "true",
                length=len(node.get("text", "")),
            )
    return None


def can_type(value: str) -> bool:
    return "%s" not in value and all(" " <= character <= "~" for character in value)


def type_value(session: DeviceSession, value: str, *, password: bool) -> FocusedField:
    if not can_type(value):
        raise DeviceError(
            "the value holds something the device's input command would drop or change: "
            "a character outside printable ASCII, or a percent sign followed by s. Nothing was typed."
        )
    before = focused_field(session.screen())
    if before is None:
        raise DeviceError("no editable field has focus. Tap the field first, for example with Maestro, then retry.")
    if password and not before.is_password:
        raise DeviceError(
            f"the focused field {before.resource_id or '(no id)'} in {before.package} is not a password field. "
            "A password typed there shows on screen and in every screen read. Nothing was typed."
        )
    session.type_text(value)
    after = focused_field(session.screen())
    if after is None or (after.package, after.resource_id) != (before.package, before.resource_id):
        raise DeviceError("the focus moved while typing, so the value may have reached another field. Check the screen before you retry.")
    if after.length != len(value):
        raise DeviceError(
            f"the field holds {after.length} characters after typing {len(value)}. "
            "It held text already, or it dropped or changed characters. Clear it before you retry."
        )
    return after
