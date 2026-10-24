"""How a command reaches the counter: over the daemon's socket or in this process."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from saddlebag import browser, protocol
from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import KeyringStore, open_door, secret_service_accounts
from saddlebag.preference import read as read_preference
from saddlebag.protocol import DaemonNotRunning, ProtocolError, Reply, Request
from saddlebag.store import RouteError, SecretStore
from saddlebag.verbs import Verbs

__all__ = ["InProcessRoute", "Route", "RouteError", "SocketRoute", "choose"]


class Route(Protocol):
    """Takes a request to a counter and brings its reply back."""

    def ask(self, request: Request) -> Reply: ...


class SocketRoute:
    """Sends the request to a running daemon."""

    def ask(self, request: Request) -> Reply:
        return protocol.send(request)


class InProcessRoute:
    """Answers the request in this process over a store."""

    def __init__(self, store: SecretStore) -> None:
        self._verbs = Verbs(store, browser.DEFAULT_ENDPOINT, "in-process")

    def ask(self, request: Request) -> Reply:
        return self._verbs.handle(request)


def _keyring_route() -> Route:
    return InProcessRoute(KeyringStore(Catalogue.default(), open_door(), secret_service_accounts))


def _daemon_answers(path: Path) -> bool:
    """Whether a saddlebag daemon answers a ping on ``path``; a stale socket file is not an answer."""
    if not path.exists():
        return False
    stranger = RouteError(f"something listens on {path} but does not answer saddlebag ping: stop it or point SADDLEBAG_SOCKET elsewhere")
    try:
        reply = protocol.send(Request("ping"), timeout=2.0)
    except DaemonNotRunning as exc:
        if protocol.is_live(path):
            raise stranger from exc
        return False
    except ProtocolError as exc:
        raise stranger from exc
    if not reply.ok or "version" not in reply.result:
        raise stranger
    return True


def choose(environ: Mapping[str, str] = os.environ) -> Route:
    """The route for this session: the operator's preference, a named socket, a daemon that answers, else the keyring."""
    preference = read_preference(environ)
    if preference is not None:
        return SocketRoute() if preference.backend == "daemon" else _keyring_route()
    if environ.get("SADDLEBAG_SOCKET"):
        return SocketRoute()
    if _daemon_answers(protocol.socket_path()):
        return SocketRoute()
    return _keyring_route()
