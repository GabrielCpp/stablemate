"""What `doctor` says about the Keychain interpreter, and how a closed door stops every verb."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import keyring_store, verbs
from saddlebag.store import StoreUnavailable
from conftest import FakeBackend

Run = Callable[..., int]


@pytest.fixture
def mac_backend(keyring_route: FakeBackend, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeBackend:
    mac = type("Keyring", (FakeBackend,), {"__module__": "keyring.backends.macOS"})()
    monkeypatch.setattr("saddlebag.route.open_door", lambda: mac)
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    return mac


def test_doctor_prints_the_interpreter_on_macos(mac_backend: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("doctor") == 0
    assert f"interpreter: {sys.executable}" in capsys.readouterr().out


def test_doctor_json_carries_the_interpreter_on_macos(mac_backend: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("doctor", "--json") == 0
    assert json.loads(capsys.readouterr().out)["interpreter"] == sys.executable


def test_doctor_prints_no_interpreter_elsewhere(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("doctor") == 0
    assert "interpreter:" not in capsys.readouterr().out
    assert run("doctor", "--json") == 0
    assert json.loads(capsys.readouterr().out)["interpreter"] is None


@pytest.mark.parametrize(
    "argv",
    [("list",), ("tags",), ("doctor",), ("secret", "create", "x"), ("exec", "--tag", "a=b", "--", "true")],
)
def test_a_closed_door_stops_every_verb(argv: tuple[str, ...], keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def closed() -> FakeBackend:
        raise StoreUnavailable(keyring_store.LOCKED)

    monkeypatch.setattr("saddlebag.route.open_door", closed)
    assert run(*argv) == 1
    assert "the OS keyring is locked" in capsys.readouterr().err
