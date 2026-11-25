from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, Callable, Mapping, cast

from ostler.book.cast import SOLE, Actor
from ostler.book.errors import BookError, Unhealthy
from ostler.book.http_identities import Identities, Reference, Reply
from ostler.book.http_objects import Auth, error_field
from ostler.book.http_paths import Witness
from ostler.book.signed import Signed
from ostler.book.status import Status

if TYPE_CHECKING:
    from ostler.book.http_endpoint import Endpoint


class Undeclared(Exception):
    """The app answered with a status the endpoint does not declare."""

    def __init__(self, endpoint: type[Endpoint], status: Status, body: object):
        super().__init__(f"{endpoint.__name__} answered {status}, which it does not declare; body {body!r}")
        self.status = status


class OffShape(Exception):
    """The app's body does not fit the shape declared for that status."""

    def __init__(self, endpoint: type[Endpoint], status: Status, mismatches: list[str]):
        super().__init__(f"{endpoint.__name__} answered {status} with a body off its shape: " + "; ".join(mismatches))
        self.mismatches = mismatches


class Client:
    """Where the service listens and the credentials each caller holds, one per
    scheme. `credentials` are the sole caller's. `send` is the one way through."""

    def __init__(self, base: str, credentials: Mapping[Auth, str | Signed] | None = None, timeout: float = 10,
                 message_of: Callable[[object], str] = error_field, hosts: Mapping[str, str] | None = None):
        self.base = base.rstrip("/")
        self.message_of = message_of
        self.hosts = {name: address.rstrip("/") for name, address in (hosts or {}).items()}
        self.held: dict[tuple[Actor, Auth], str | Signed] = {(SOLE, auth): value for auth, value in (credentials or {}).items()}
        self.timeout = timeout
        self.ids = Identities()
        self.witness = Witness()
        self.known: dict[str, object] = {}
        self.resolved: dict[str, Any] = {}

    def know(self, name: str, value: object) -> None:
        """Say what the reference `name` stands for: a value, or a callable
        that returns it, called once on first use."""
        self.known[name] = value
        self.resolved.pop(name, None)

    def resolve(self, reference: Reference) -> Any:
        if reference.name not in self.resolved:
            if reference.name not in self.known:
                raise BookError(f"the client knows nothing called {reference.name!r}; register it with client.know")
            value = self.known[reference.name]
            self.resolved[reference.name] = cast(Callable[[], Any], value)() if callable(value) else value
        return self.resolved[reference.name]

    def hold(self, actor: Actor, auth: Auth, credential: str | Signed) -> None:
        """Keep the credential `actor` presents under `auth`."""
        self.held[(actor, auth)] = credential

    def forget(self) -> None:
        self.witness.settle()
        self.ids.clear()

    def address(self, host: str) -> str:
        if not host:
            return self.base
        if host not in self.hosts:
            raise BookError(f"the client knows no host called {host!r}")
        return self.hosts[host]

    def send(self, call: Endpoint) -> Reply:
        return call.send(self)

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[Status, bytes]:
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as reply:
                return reply.status, reply.read()
        except urllib.error.HTTPError as reply:
            return reply.code, reply.read()
        except (urllib.error.URLError, OSError) as down:
            raise Unhealthy(f"{method} {url} did not answer: {getattr(down, 'reason', down)}") from None
