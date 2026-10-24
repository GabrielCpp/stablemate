"""Which route a command takes."""

from __future__ import annotations

from pathlib import Path

import pytest

from saddlebag import protocol, route
from saddlebag.catalogue import Catalogue
from saddlebag.protocol import DaemonNotRunning, Request
from saddlebag.route import InProcessRoute, RouteError, SocketRoute

from conftest import FakeBackend


@pytest.fixture
def keyring_door(backend: FakeBackend, catalogue: Catalogue, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Catalogue, "default", classmethod(lambda cls: catalogue))
    monkeypatch.setattr(route, "open_door", lambda: backend)


def test_backend_daemon_chooses_the_socket() -> None:
    assert isinstance(route.choose({"SADDLEBAG_BACKEND": "daemon"}), SocketRoute)


def test_backend_keyring_chooses_the_keyring(keyring_door: None) -> None:
    assert isinstance(route.choose({"SADDLEBAG_BACKEND": "keyring"}), InProcessRoute)


def test_an_unknown_backend_is_refused() -> None:
    with pytest.raises(RouteError, match="unknown SADDLEBAG_BACKEND 'bogus'"):
        route.choose({"SADDLEBAG_BACKEND": "bogus"})


def test_a_named_socket_with_nothing_listening_never_falls_to_the_keyring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SADDLEBAG_SOCKET", str(tmp_path / "none.sock"))
    chosen = route.choose({"SADDLEBAG_SOCKET": str(tmp_path / "none.sock")})
    assert isinstance(chosen, SocketRoute)
    with pytest.raises(DaemonNotRunning, match="saddlebag serve"):
        chosen.ask(Request("ping"))


def test_a_live_socket_chooses_the_daemon(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(protocol, "socket_path", lambda: tmp_path / "live.sock")
    monkeypatch.setattr(protocol, "is_live", lambda path: True)
    assert isinstance(route.choose({}), SocketRoute)


def test_nothing_set_and_no_socket_chooses_the_keyring(keyring_door: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(protocol, "socket_path", lambda: tmp_path / "none.sock")
    monkeypatch.setattr(protocol, "is_live", lambda path: False)
    assert isinstance(route.choose({}), InProcessRoute)


def test_a_missing_keyring_surfaces_when_the_keyring_route_is_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    from saddlebag.store import StoreUnavailable

    def absent() -> FakeBackend:
        raise StoreUnavailable("no OS keyring on this session")

    monkeypatch.setattr(route, "open_door", absent)
    with pytest.raises(StoreUnavailable, match="no OS keyring"):
        route.choose({"SADDLEBAG_BACKEND": "keyring"})
    assert isinstance(route.choose({"SADDLEBAG_BACKEND": "daemon"}), SocketRoute)
