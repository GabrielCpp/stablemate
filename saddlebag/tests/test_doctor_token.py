"""`doctor` names where the daemon's Vault token came from."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import verbs
from saddlebag.daemon import serve
from conftest import FakeBackend, FakeVault, Running

import threading

Run = Callable[..., int]

WARNING = "warning: the Vault token is read from a file; any process of this user can read it. Prefer saddlebag serve --keep-token."


def test_doctor_prints_the_token_source_and_the_file_warning(vault: FakeVault, daemon_path: Path, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    ready, stop = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=serve,
        args=(vault,),
        kwargs={"socket_path": daemon_path, "ready": ready, "stop": stop, "token_source": "file /x/vault-token"},
    )
    thread.start()
    assert ready.wait(5)
    try:
        assert run("doctor") == 0
    finally:
        stop.set()
        thread.join(timeout=5)
    out = capsys.readouterr().out
    assert "token source: file /x/vault-token" in out
    assert WARNING in out


def test_doctor_names_a_stdin_token_without_the_file_warning(running: Running, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("doctor") == 0
    assert "token source" not in capsys.readouterr().out


def test_doctor_on_the_keyring_route_prints_no_token_source(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("doctor") == 0
    assert "token source" not in capsys.readouterr().out


def test_doctor_on_the_keyring_route_words_the_token_file_warning_for_this_host(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    present = tmp_path / "vault-token"
    present.write_text("x")
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", present)
    assert run("doctor") == 0
    assert "warning: ~/.vault-token exists; any process of this user can read it" in capsys.readouterr().out
