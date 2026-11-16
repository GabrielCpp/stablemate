"""The API as a surface: ostler sends every step as declared; this keeps the
credentials and the way the app is put back to its first state."""

from __future__ import annotations

import json
from datetime import date

from ostler.book import Actor, ApiKey, Bearer, BookError, Client, Endpoint, Environment
from ostler.book.http import Reply
from ostler.book.httpsurface import HttpSurface

from .endpoints import ReadClock, Reset


class TodoApi(HttpSurface):
    def __init__(self, environment: Environment):
        super().__init__(Client(environment.address("api"), {Bearer(): "test-token", ApiKey(): "test-key"}))
        self.accounts: dict[Actor, dict[str, str]] = {}

    def restore(self) -> None:
        Reset().send(self.client)
        for actor in self.accounts:
            self.client.held.pop((actor, Bearer()), None)
        self.accounts = {}

    def send(self, call: Endpoint) -> Reply:
        if call.by is not None and call.by.fresh:
            self.account(call.by)
        return super().send(call)

    def account(self, actor: Actor) -> dict[str, str]:
        """What a person types to sign in as `actor`: the service makes the account the first time it is asked for, and the
        client holds the token that account signs in for."""
        if actor not in self.accounts:
            made = self.post("/admin/persons", {"handle": actor.handle})
            token = self.post("/sign-in", {"handle": made["handle"], "password": made["password"]})["token"]
            self.client.hold(actor, Bearer(), token)
            self.accounts[actor] = {"handle": made["handle"], "password": made["password"]}
        return self.accounts[actor]

    def post(self, path: str, body: dict[str, str]) -> dict[str, str]:
        status, raw = self.client.transport("POST", self.client.base + path, {"Content-Type": "application/json"},
                                            json.dumps(body).encode())
        if status not in (200, 201):
            raise BookError(f"POST {path} answered {status}: {raw.decode(errors='replace')}")
        return json.loads(raw)

    def today(self) -> date:
        return date.fromisoformat(ReadClock().send(self.client).body["today"])
