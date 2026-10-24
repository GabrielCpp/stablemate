"""The three token sources, their order and the places a token is refused."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from saddlebag import custody
from saddlebag.custody import EMPTY, REFUSED, TOKEN_ACCOUNT, TOKEN_SERVICE, CustodyError, Token
from saddlebag.store import StoreUnavailable
from conftest import FakeBackend

STAND_IN = "s.stand-in"


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def filed_token(path: Path, text: str = STAND_IN, mode: int = 0o600) -> Path:
    path.write_text(text)
    path.chmod(mode)
    return path


def test_the_environment_is_refused() -> None:
    with pytest.raises(CustodyError, match="VAULT_TOKEN") as exc:
        custody.refuse_environment({"VAULT_TOKEN": "x"})
    assert str(exc.value) == REFUSED
    custody.refuse_environment({})


def test_piped_reads_one_line() -> None:
    assert custody.piped(io.StringIO(f"  {STAND_IN}  \n")) == Token(STAND_IN, "stdin")


def test_piped_refuses_an_empty_line() -> None:
    with pytest.raises(CustodyError) as exc:
        custody.piped(io.StringIO("\n"))
    assert str(exc.value) == EMPTY


def test_piped_leaves_a_terminal_alone() -> None:
    stdin = Terminal(f"{STAND_IN}\n")
    assert custody.piped(stdin) is None
    assert stdin.tell() == 0


def test_kept_reads_the_keyring(backend: FakeBackend) -> None:
    assert custody.kept(lambda: backend) is None
    backend.items[(TOKEN_SERVICE, TOKEN_ACCOUNT)] = STAND_IN
    assert custody.kept(lambda: backend) == Token(STAND_IN, "keyring")


def test_kept_is_none_when_the_keyring_is_unavailable() -> None:
    def door() -> FakeBackend:
        raise StoreUnavailable("no keyring")

    assert custody.kept(door) is None


def test_filed_is_none_for_a_missing_path(tmp_path: Path) -> None:
    assert custody.filed(tmp_path / "vault-token") is None


def test_filed_refuses_a_loose_mode(tmp_path: Path) -> None:
    path = filed_token(tmp_path / "vault-token", mode=0o644)
    with pytest.raises(CustodyError, match="refusing .* 0644") as exc:
        custody.filed(path)
    assert STAND_IN not in str(exc.value)


def test_filed_reads_a_private_file(tmp_path: Path) -> None:
    path = filed_token(tmp_path / "vault-token", f"{STAND_IN}\n")
    assert custody.filed(path) == Token(STAND_IN, f"file {path}")


def test_filed_refuses_an_empty_file(tmp_path: Path) -> None:
    path = filed_token(tmp_path / "vault-token", "\n")
    with pytest.raises(CustodyError, match="is empty"):
        custody.filed(path)


def test_find_prefers_piped_then_kept_then_filed(backend: FakeBackend, tmp_path: Path) -> None:
    path = filed_token(tmp_path / "vault-token", "s.filed")
    backend.items[(TOKEN_SERVICE, TOKEN_ACCOUNT)] = "s.kept"
    assert custody.find(io.StringIO("s.piped\n"), lambda: backend, path).source == "stdin"
    assert custody.find(Terminal(), lambda: backend, path) == Token("s.kept", "keyring")
    del backend.items[(TOKEN_SERVICE, TOKEN_ACCOUNT)]
    assert custody.find(Terminal(), lambda: backend, path) == Token("s.filed", f"file {path}")


def test_find_without_a_token_names_the_path(backend: FakeBackend, tmp_path: Path) -> None:
    path = tmp_path / "vault-token"
    with pytest.raises(CustodyError, match="no Vault token") as exc:
        custody.find(Terminal(), lambda: backend, path)
    assert str(path) in str(exc.value)


def test_keep_stores_the_token_without_printing_it(backend: FakeBackend, capsys: pytest.CaptureFixture[str]) -> None:
    custody.keep(io.StringIO(f"{STAND_IN}\n"), lambda: backend)
    assert backend.items == {(TOKEN_SERVICE, TOKEN_ACCOUNT): STAND_IN}
    captured = capsys.readouterr()
    assert STAND_IN not in captured.out + captured.err


def test_keep_refuses_an_empty_line(backend: FakeBackend) -> None:
    with pytest.raises(CustodyError):
        custody.keep(io.StringIO("\n"), lambda: backend)
    assert backend.items == {}


@pytest.mark.parametrize("state", ["/Users/x/Library/Application Support/stablemate", "/home/x/.local/state/stablemate"])
def test_filed_path_sits_under_the_state_dir(state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platformdirs.user_state_dir", lambda appname: state)
    assert custody.filed_path() == Path(state) / "saddlebag" / "vault-token"
    assert str(custody.filed_path()).endswith("saddlebag/vault-token")
