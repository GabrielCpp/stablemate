"""Shared fixtures: a dict-backed Vault, a daemon on a temp socket and a CLI runner."""

from __future__ import annotations

import io
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import keyring.errors
import pytest
from keyring.backend import KeyringBackend
from keyring.compat import properties

from saddlebag import browser, cli, daemon, protocol
from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import SERVICE
from saddlebag.models import Secret, Tag
from saddlebag.protocol import Reply, Request
from saddlebag.store import StoreHealth


class FakeVault:
    """An in-memory :class:`~saddlebag.store.SecretStore`."""

    def __init__(self) -> None:
        self.metadata: dict[str, Secret] = {}
        self.data: dict[str, dict[str, str]] = {}
        self.authenticated = True

    def health(self) -> StoreHealth:
        return StoreHealth("vault", self.authenticated)

    def names(self) -> list[str]:
        return sorted(self.metadata)

    def get(self, name: str) -> Secret | None:
        secret = self.metadata.get(name)
        if secret is None:
            return None
        return replace(secret, fields=frozenset(self.data.get(name, {})))

    def create(self, secret: Secret) -> None:
        self.metadata[secret.name] = replace(secret, fields=frozenset())
        self.data.setdefault(secret.name, {})

    def set_value(self, name: str, field: str, value: str) -> None:
        self.data[name][field] = value

    def unset_value(self, name: str, field: str) -> None:
        self.data[name].pop(field, None)

    def remove(self, name: str) -> None:
        self.metadata.pop(name, None)
        self.data.pop(name, None)

    def value(self, name: str, field: str) -> str | None:
        if field == "username":
            return self.metadata[name].username
        return self.data[name].get(field)

    def retag(self, name: str, tags: frozenset[Tag]) -> None:
        self.metadata[name] = replace(self.metadata[name], tags=tags)


class FakeBackend(KeyringBackend):
    """A dict-backed keyring backend."""

    @properties.classproperty
    def priority(cls) -> float:
        return 1.0

    def __init__(self) -> None:
        super().__init__()
        self.items: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.items:
            raise keyring.errors.PasswordDeleteError("Password not found")
        del self.items[(service, username)]


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "stablemate-config" / "config.toml"
    monkeypatch.setenv("STABLEMATE_CONFIG", str(path))
    return path


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def catalogue(tmp_path: Path) -> Catalogue:
    return Catalogue(tmp_path / "state" / "catalogue.json")


@pytest.fixture
def keyring_route(backend: FakeBackend, catalogue: Catalogue, monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    monkeypatch.setenv("SADDLEBAG_BACKEND", "keyring")
    monkeypatch.setattr(Catalogue, "default", classmethod(lambda cls: catalogue))
    monkeypatch.setattr("saddlebag.route.open_door", lambda: backend)
    monkeypatch.setattr(
        "saddlebag.route.secret_service_accounts",
        lambda: sorted(account for service, account in backend.items if service == SERVICE),
    )
    return backend


@pytest.fixture
def vault() -> FakeVault:
    return FakeVault()


@dataclass
class Running:
    """A daemon serving ``vault`` on ``path``."""

    path: Path
    vault: FakeVault

    def ask(self, verb: str, **args: object) -> Reply:
        return protocol.send(Request(verb, dict(args)), timeout=10)


@pytest.fixture
def daemon_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SADDLEBAG_SOCKET", str(tmp_path / "sb.sock"))
    return protocol.socket_path()


@pytest.fixture
def running(vault: FakeVault, daemon_path: Path) -> Iterator[Running]:
    ready, stop = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=daemon.serve,
        args=(vault,),
        kwargs={"socket_path": daemon_path, "ready": ready, "stop": stop},
    )
    thread.start()
    assert ready.wait(5)
    try:
        yield Running(daemon_path, vault)
    finally:
        stop.set()
        thread.join(timeout=5)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Callable[..., int]:
    def _run(*argv: str, stdin: str | None = None) -> int:
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            cli.main(list(argv))
        code = exc.value.code
        assert isinstance(code, int)
        return code

    return _run


class RecordingSession:
    """Stands in for the page's WebSocket."""

    last: RecordingSession | None = None

    def __init__(self, websocket_url: str) -> None:
        self.websocket_url = websocket_url
        self.typed: str | None = None
        self.closed = False
        RecordingSession.last = self

    def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "Input.insertText":
            self.typed = params["text"]
            return {}
        if "el.focus()" in params["expression"]:
            return {"result": {"value": {"found": True, "editable": True, "tag": "INPUT", "type": "password"}}}
        return {"result": {"value": len(self.typed or "")}}

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_browser(monkeypatch: pytest.MonkeyPatch) -> tuple[browser.Target, ...]:
    """One open page at the login URL, and a session that records what is typed."""
    pages = (
        browser.Target(id="a", url="https://github.com/login", title="", websocket_url="ws://127.0.0.1:9222/a"),
    )
    monkeypatch.setattr(browser, "list_targets", lambda endpoint: pages)
    monkeypatch.setattr(browser, "WebSocketSession", RecordingSession)
    RecordingSession.last = None
    return pages
