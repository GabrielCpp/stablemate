"""The API as a surface: ostler sends every step as declared; this keeps the
credentials and the way the app is put back to its first state."""

from __future__ import annotations

from datetime import date

from ostler.book import ApiKey, Bearer, Client, Environment
from ostler.book.httpsurface import HttpSurface

from .endpoints import ReadClock, Reset


class TodoApi(HttpSurface):
    def __init__(self, environment: Environment):
        super().__init__(Client(environment.address("api"), {Bearer(): "test-token", ApiKey(): "test-key"}))

    def restore(self) -> None:
        Reset().send(self.client)

    def today(self) -> date:
        return date.fromisoformat(ReadClock().send(self.client).body["today"])
