"""A secret's value for Python code that consumes it in process."""

from __future__ import annotations

from saddlebag import protocol, route
from saddlebag.protocol import DaemonNotRunning, Request
from saddlebag.store import RouteError, StoreUnavailable

__all__ = ["SecretUnavailable", "secret_value"]

_VAR = "SADDLEBAG_VALUE"


class SecretUnavailable(RuntimeError):
    """The route refused, or the secret or its field is unknown. The message is saddlebag's own."""


def secret_value(name: str, field: str = "password") -> str:
    """The value of ``field`` of the secret ``name``, through the route this session uses."""
    request = Request("env", {"bindings": [{"var": _VAR, "name": name, "field": field}]})
    try:
        reply = route.choose().ask(request)
    except (DaemonNotRunning, StoreUnavailable, RouteError) as exc:
        raise SecretUnavailable(str(exc)) from exc
    except protocol.ProtocolError as exc:
        raise SecretUnavailable(f"the daemon sent an unreadable reply: {exc}") from exc
    if not reply.ok:
        raise SecretUnavailable(reply.error or f"cannot read {name}")
    values = reply.result.get("values")
    if not isinstance(values, dict) or not isinstance(values.get(_VAR), str):
        raise SecretUnavailable(f"the reply carried no value for {name}")
    return values[_VAR]
