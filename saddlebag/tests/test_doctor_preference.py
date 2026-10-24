"""Where `doctor` says the route choice came from."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import protocol, route, verbs
from conftest import FakeBackend

Run = Callable[..., int]


def test_doctor_names_the_environment_as_the_source(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("doctor") == 0
    assert "preference: keyring (SADDLEBAG_BACKEND)" in capsys.readouterr().out


def test_doctor_says_auto_when_nothing_is_set(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SADDLEBAG_BACKEND")
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    monkeypatch.setattr(protocol, "socket_path", lambda: tmp_path / "none.sock")
    monkeypatch.setattr(route, "_daemon_answers", lambda path: False)
    assert run("doctor") == 0
    assert "preference: none (auto)" in capsys.readouterr().out


def test_doctor_json_carries_the_preference(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("doctor", "--json") == 0
    assert json.loads(capsys.readouterr().out)["preference"] == {"backend": "keyring", "source": "SADDLEBAG_BACKEND"}
