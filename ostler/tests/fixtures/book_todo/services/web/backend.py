"""The API behind the web app, reached through the test hooks it offers: a fresh store, a moved clock, a store that
is down. The web app itself never calls them."""

from __future__ import annotations

import json
from datetime import date
from urllib.request import Request, urlopen


class Backend:
    def __init__(self, base: str):
        self.base = base

    def send(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, str]:
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method)
        with urlopen(request) as answer:
            text = answer.read()
        return json.loads(text) if text else {}

    def reset(self) -> None:
        self.send("POST", "/admin/reset", {})

    def today(self) -> date:
        return date.fromisoformat(self.send("GET", "/admin/clock")["today"])

    def set_today(self, today: date) -> None:
        self.send("POST", "/admin/clock", {"today": today.isoformat()})

    def store_down(self, down: bool) -> None:
        self.send("POST", "/admin/store", {"down": down})
