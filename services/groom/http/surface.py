"""groom's HTTP API as a surface: ostler sends every step as declared; this keeps the
address and the way the app is put back to its first state."""

from __future__ import annotations

import json
from datetime import date

from ostler.book import Client, Environment
from ostler.book.httpsurface import HttpSurface

from ..fixtures import Settings
from .endpoints import SetAttend


def message_of(body: object) -> str:
    """The reason groom gives: `detail` on the framework's refusals, `error` on a dispatch queue's."""
    if isinstance(body, dict):
        for key in ("detail", "error"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return ""


TEXT_FIELDS = ("name", "repo_name", "repo_branch", "current_node")


class HealingClient(Client):
    """After a push that stored a field as something other than text, groom's fleet answers
    500 until that run is pushed again with text. This client pushes the run again, so a
    wrong-typed input leaves later cells a fleet that still answers."""

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None):
        reply = super().transport(method, url, headers, data)
        if data is not None and "/push/" in url:
            self._heal(url, headers, data)
        return reply

    def _heal(self, url: str, headers: dict[str, str], data: bytes) -> None:
        try:
            body = json.loads(data)
        except ValueError:
            return
        if not isinstance(body, dict) or body.get("container_id") is None:
            return
        if all(body.get(field) is None or isinstance(body[field], str) for field in TEXT_FIELDS):
            return
        cid = str(body["container_id"])[:12]
        fix = {"container_id": cid, "name": cid, "repo_name": "", "repo_branch": "", "current_node": ""}
        base = url.split("/push/")[0]
        super().transport("POST", base + "/push/progress", headers, json.dumps(fix).encode())


class GroomApi(HttpSurface):
    def __init__(self, environment: Environment):
        super().__init__(HealingClient(environment.address("api"), {}, message_of=message_of))

    def restore(self) -> None:
        SetAttend(Settings(enabled=False)).send(self.client)

    def today(self) -> date:
        return date.today()
