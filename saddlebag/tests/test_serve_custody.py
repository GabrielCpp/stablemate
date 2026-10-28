"""`serve` takes its Vault token from stdin, the OS keyring or a private file, and `--keep-token` fills the keyring."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import custody, daemon
from saddlebag.custody import REFUSED, TOKEN_ACCOUNT, TOKEN_SERVICE
from conftest import FakeBackend

Run = Callable[..., int]

STAND_IN = "s.stand-in"
ADDR = "http://vault.example.com:8200"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def seen(backend: FakeBackend, daemon_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    record: dict[str, object] = {}

    def connect(addr: str, token: str) -> object:
        record.update(token=token)
        return object()

    def serve(store: object, *, socket_path: Path, browser_endpoint: str, stop: object, token_source: str | None) -> None:
        record.update(source=token_source)

    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setattr("saddlebag.keyring_store.open_door", lambda: backend)
    monkeypatch.setattr("saddlebag.vault.VaultStore", connect)
    monkeypatch.setattr(daemon, "serve", serve)
    monkeypatch.setattr(custody, "filed_path", lambda: daemon_path.parent / "absent-token")
    return record


def test_serve_uses_the_kept_token_on_a_terminal(run: Run, seen: dict[str, object], backend: FakeBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    backend.items[(TOKEN_SERVICE, TOKEN_ACCOUNT)] = STAND_IN
    monkeypatch.setattr("sys.stdin", Terminal())
    assert run("serve", "--vault-addr", ADDR) == 0
    assert seen == {"token": STAND_IN, "source": "keyring"}


def test_serve_prefers_the_piped_token(run: Run, seen: dict[str, object], backend: FakeBackend) -> None:
    backend.items[(TOKEN_SERVICE, TOKEN_ACCOUNT)] = "s.kept"
    assert run("serve", "--vault-addr", ADDR, stdin=f"{STAND_IN}\n") == 0
    assert seen == {"token": STAND_IN, "source": "stdin"}


def test_serve_falls_back_to_the_private_file(run: Run, seen: dict[str, object], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "vault-token"
    path.write_text(STAND_IN)
    path.chmod(0o600)
    monkeypatch.setattr(custody, "filed_path", lambda: path)
    monkeypatch.setattr("sys.stdin", Terminal())
    assert run("serve", "--vault-addr", ADDR) == 0
    assert seen == {"token": STAND_IN, "source": f"file {path}"}


def test_serve_without_any_token_exits_two(run: Run, seen: dict[str, object], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", Terminal())
    assert run("serve", "--vault-addr", ADDR) == 2
    assert "no Vault token" in capsys.readouterr().err
    assert seen == {}


def test_keep_token_stores_the_piped_token(run: Run, seen: dict[str, object], backend: FakeBackend, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("serve", "--keep-token", stdin=f"{STAND_IN}\n") == 0
    assert backend.items == {(TOKEN_SERVICE, TOKEN_ACCOUNT): STAND_IN}
    captured = capsys.readouterr()
    assert STAND_IN not in captured.out + captured.err
    assert seen == {}


def test_keep_token_still_refuses_the_environment(run: Run, seen: dict[str, object], backend: FakeBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("VAULT_TOKEN", "root")
    assert run("serve", "--keep-token", stdin=f"{STAND_IN}\n") == 2
    assert REFUSED in capsys.readouterr().err
    assert backend.items == {}
