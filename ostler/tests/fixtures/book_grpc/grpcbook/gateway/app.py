"""The gateway in front of the teams service: an HTTP face over its gRPC calls, in the process of the test.
It keeps nothing and answers from the owner it is handed."""

from __future__ import annotations

import json
from typing import Any

from ostler.book import Client, Code, GrpcClient
from ostler.book.status import Status


class Gateway:
    def __init__(self, owner: GrpcClient, bug: str | None = None):
        self.owner = owner
        self.bug = bug

    def call(self, method: str, body: dict[str, Any]) -> tuple[Status, Any]:
        status, raw = self.owner.transport("POST", f"{self.owner.base}/acme.Teams/{method}", {}, json.dumps(body).encode())
        return status, json.loads(raw) if raw else None

    def read(self, ident: str) -> tuple[int, Any]:
        status, body = self.call("Get", {"id": ident})
        if status is Code.NOT_FOUND:
            return (500, {"error": "Internal Server Error"}) if self.bug == "gateway-hides-missing" else (404, {"error": "no such team"})
        assert body is not None
        label = "" if self.bug == "gateway-mislabels" else body["name"]
        return 200, {"id": body["id"], "label": label}

    def done(self, ident: str) -> tuple[int, Any]:
        if self.bug == "gateway-drops-done":
            return 204, None
        status, _ = self.call("Remove", {"id": ident})
        return (404, {"error": "no such team"}) if status is Code.NOT_FOUND else (204, None)


class GatewayClient(Client):
    """A client whose requests the gateway answers in process, as a service on a port would."""

    def __init__(self, gateway: Gateway):
        super().__init__("http://gateway.local")
        self.gateway = gateway

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[Status, bytes]:
        path = url.removeprefix(self.base)
        if method == "GET" and path.startswith("/gateway/"):
            status, payload = self.gateway.read(path.removeprefix("/gateway/"))
        elif method == "POST" and path.startswith("/gateway/") and path.endswith("/done"):
            status, payload = self.gateway.done(path.removeprefix("/gateway/").removesuffix("/done"))
        else:
            status, payload = 404, {"error": "Not found"}
        return status, b"" if payload is None else json.dumps(payload).encode()
