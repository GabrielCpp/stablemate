"""Typing into a device's focused field: what is refused, what comes back, what reaches adb."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from saddlebag import device

from conftest import FakeDevice

VALUE = "hunter2-pw"


def test_a_field_that_takes_the_value_reports_its_length_and_identity() -> None:
    session = FakeDevice()
    typed = device.type_value(session, VALUE, password=True)
    assert session.typed == [VALUE]
    assert typed == device.FocusedField("com.acme.app", "com.acme.app:id/entry", True, len(VALUE))


def test_a_password_is_refused_on_a_field_that_would_show_it() -> None:
    session = FakeDevice(password=False)
    with pytest.raises(device.DeviceError, match="not a password field"):
        device.type_value(session, VALUE, password=True)
    assert session.typed == []


def test_a_username_goes_to_a_plain_field() -> None:
    session = FakeDevice(password=False)
    assert device.type_value(session, "gab", password=False).length == 3


def test_nothing_is_typed_when_no_field_has_focus() -> None:
    session = FakeDevice(focused=False)
    with pytest.raises(device.DeviceError, match="no editable field has focus"):
        device.type_value(session, VALUE, password=True)
    assert session.typed == []


def test_a_focused_button_does_not_count_as_a_field() -> None:
    session = FakeDevice(widget="android.widget.Button")
    with pytest.raises(device.DeviceError, match="no editable field has focus"):
        device.type_value(session, VALUE, password=True)


def test_a_login_template_autocomplete_field_counts_as_a_field() -> None:
    session = FakeDevice(password=False, widget="android.widget.AutoCompleteTextView")
    assert device.type_value(session, "gab", password=False).length == 3


@pytest.mark.parametrize("value", ["ab%scd", "café", "\U0001f600", "tab\there", "line\nbreak"])
def test_a_value_the_input_command_would_change_is_refused_before_the_device_is_touched(value: str) -> None:
    session = FakeDevice()
    with pytest.raises(device.DeviceError) as caught:
        device.type_value(session, value, password=True)
    assert session.typed == [] and session.screens == 0
    assert value not in str(caught.value)


@pytest.mark.parametrize("value", ["50%", "a b", "$'\"&;\\", "-dash", "~!@#^*()_+={}[]|:<>,.?/"])
def test_awkward_printable_values_are_allowed(value: str) -> None:
    assert device.can_type(value)


def test_a_field_that_already_held_text_is_an_error_with_counts_only() -> None:
    session = FakeDevice(text="old")
    with pytest.raises(device.DeviceError, match="holds 13 characters after typing 10") as caught:
        device.type_value(session, VALUE, password=True)
    assert VALUE not in str(caught.value)


def test_dropped_characters_are_an_error() -> None:
    class Dropping(FakeDevice):
        def type_text(self, value: str) -> None:
            super().type_text(value[:-1])

    with pytest.raises(device.DeviceError, match="holds 9 characters after typing 10"):
        device.type_value(Dropping(), VALUE, password=True)


def test_focus_lost_while_typing_is_an_error() -> None:
    class Blurring(FakeDevice):
        def type_text(self, value: str) -> None:
            self.focused = False

    with pytest.raises(device.DeviceError, match="focus moved"):
        device.type_value(Blurring(), VALUE, password=True)


def test_focus_moved_to_another_field_while_typing_is_an_error() -> None:
    class Moved(FakeDevice):
        def screen(self) -> str:
            shown = super().screen()
            return shown.replace("id/entry", "id/other") if self.typed else shown

    with pytest.raises(device.DeviceError, match="focus moved"):
        device.type_value(Moved(), VALUE, password=True)


def test_a_plain_fields_text_stays_out_of_what_is_returned() -> None:
    session = FakeDevice(password=False)
    typed = device.type_value(session, VALUE, password=False)
    assert VALUE not in repr(typed)


def test_a_broken_screen_is_an_error_that_quotes_nothing() -> None:
    with pytest.raises(device.DeviceError) as caught:
        device.focused_field(f'<hierarchy><node text="{VALUE}"')
    assert VALUE not in str(caught.value)


def test_the_only_ready_device_is_picked() -> None:
    assert device.select_serial({"emulator-5554": "device", "emulator-5556": "offline"}, None) == "emulator-5554"


def test_several_ready_devices_need_a_choice() -> None:
    with pytest.raises(device.DeviceError, match="2 devices are ready.*R5CT.*emulator-5554"):
        device.select_serial({"emulator-5554": "device", "R5CT": "device"}, None)
    assert device.select_serial({"emulator-5554": "device", "R5CT": "device"}, "R5CT") == "R5CT"


def test_no_device_says_so() -> None:
    with pytest.raises(device.DeviceError, match="no device is ready.*none"):
        device.select_serial({}, None)


@pytest.mark.parametrize("state", ["unauthorized", "offline"])
def test_a_named_device_that_is_not_ready_is_refused(state: str) -> None:
    with pytest.raises(device.DeviceError, match="not a ready device"):
        device.select_serial({"R5CT": state}, "R5CT")


@pytest.mark.parametrize("serial", ["192.168.1.20:5555", "localhost:5555", "adb-R5CT-abc._adb-tls-connect._tcp"])
def test_a_device_on_the_network_is_refused_named_or_not(serial: str) -> None:
    with pytest.raises(device.DeviceError, match="over the network"):
        device.select_serial({serial: "device"}, serial)
    with pytest.raises(device.DeviceError, match="over the network"):
        device.select_serial({serial: "device"}, None)


def test_adb_comes_from_path_then_the_sdk(tmp_path: Path) -> None:
    tools = tmp_path / "sdk" / "platform-tools"
    tools.mkdir(parents=True)
    (tools / "adb").write_text("")
    assert device.find_adb({"PATH": "/nonexistent", "ANDROID_HOME": str(tmp_path / "sdk")}) == str(tools / "adb")
    assert device.find_adb({"PATH": "/nonexistent", "ANDROID_SDK_ROOT": str(tmp_path / "sdk")}) == str(tools / "adb")


def test_a_missing_adb_says_how_to_fix_it() -> None:
    with pytest.raises(device.DeviceError, match="platform-tools"):
        device.find_adb({"PATH": "/nonexistent"})


class FakeAdb:
    """Stands in for the adb process: records each call and plays back its outputs."""

    def __init__(self, *outputs: subprocess.CompletedProcess[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"argv": argv, **options})
        return self.outputs.pop(0)


def finished(stdout: str = "", code: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_the_value_reaches_adb_on_stdin_and_never_on_its_command_line(monkeypatch: pytest.MonkeyPatch) -> None:
    adb = FakeAdb(finished())
    monkeypatch.setattr(subprocess, "run", adb)
    device.AdbSession("adb", "emulator-5554").type_text("it's $HOME")
    call = adb.calls[0]
    assert call["input"] == "input text 'it'\"'\"'s $HOME'\n"
    assert not any("HOME" in part or "it" == part for part in call["argv"])


def test_a_refused_input_command_does_not_repeat_what_adb_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", FakeAdb(finished(code=255, stderr=f"NullPointerException near {VALUE}")))
    with pytest.raises(device.DeviceError, match="refused the input command") as caught:
        device.AdbSession("adb", "emulator-5554").type_text(VALUE)
    assert VALUE not in str(caught.value)


def test_adb_is_pinned_to_the_local_server(monkeypatch: pytest.MonkeyPatch) -> None:
    adb = FakeAdb(finished("List of devices attached\nemulator-5554\tdevice\n\n"))
    monkeypatch.setattr(subprocess, "run", adb)
    monkeypatch.setenv("ADB_SERVER_SOCKET", "tcp:203.0.113.9:5037")
    monkeypatch.setenv("ANDROID_ADB_SERVER_ADDRESS", "203.0.113.9")
    assert device.list_devices("adb") == {"emulator-5554": "device"}
    call = adb.calls[0]
    assert call["argv"][:3] == ["adb", "-H", "127.0.0.1"]
    assert "ADB_SERVER_SOCKET" not in call["env"] and "ANDROID_ADB_SERVER_ADDRESS" not in call["env"]


def test_the_screen_survives_a_transient_failure_and_loses_its_trailer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device, "DUMP_PAUSE_SECONDS", 0)
    xml = '<hierarchy rotation="0"><node focused="false" /></hierarchy>'
    monkeypatch.setattr(
        subprocess,
        "run",
        FakeAdb(
            finished("ERROR: null root node returned by UiTestAutomationBridge.\n"),
            finished(f"<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>{xml}UI hierchary dumped to: /dev/tty\n"),
        ),
    )
    assert device.AdbSession("adb", "emulator-5554").screen() == xml


def test_a_screen_that_never_comes_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device, "DUMP_PAUSE_SECONDS", 0)
    monkeypatch.setattr(subprocess, "run", FakeAdb(*[finished("ERROR: null root\n")] * device.DUMP_ATTEMPTS))
    with pytest.raises(device.DeviceError, match="did not return its screen"):
        device.AdbSession("adb", "emulator-5554").screen()


def test_a_hung_adb_is_an_error_that_does_not_quote_its_input(monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(argv: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 30, output=VALUE)

    monkeypatch.setattr(subprocess, "run", hang)
    with pytest.raises(device.DeviceError) as caught:
        device.AdbSession("adb", "emulator-5554").type_text(VALUE)
    assert VALUE not in str(caught.value)
