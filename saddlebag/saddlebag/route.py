"""How a command reaches the counter: over the daemon's socket or in this process."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol

from saddlebag import browser, protocol
from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import KeyringStore, open_door, secret_service_accounts
from saddlebag.protocol import Reply, Request
from saddlebag.store import SecretStore
from saddlebag.verbs import Verbs


class RouteError(RuntimeError):
    """The route cannot be chosen. The message says why."""


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


def choose(environ: Mapping[str, str] = os.environ) -> Route:
    """The route for this session: an explicit choice, a named socket, a live daemon, else the keyring."""
    backend = environ.get("SADDLEBAG_BACKEND")
    if backend is not None:
        if backend == "daemon":
            return SocketRoute()
        if backend == "keyring":
            return _keyring_route()
        raise RouteError(f"unknown SADDLEBAG_BACKEND {backend!r}: expected keyring or daemon")
    if environ.get("SADDLEBAG_SOCKET"):
        return SocketRoute()
    if protocol.is_live(protocol.socket_path()):
        return SocketRoute()
    return _keyring_route()
