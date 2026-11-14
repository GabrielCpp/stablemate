"""The digest as a surface: ostler sends every step as declared; this keeps the credentials it forwards."""

from __future__ import annotations

from ostler.book import ApiKey, Bearer, Client, Environment
from ostler.book.httpsurface import HttpSurface


class DigestApi(HttpSurface):
    name = "digest"

    def __init__(self, environment: Environment):
        super().__init__(Client(environment.address("digest"), {Bearer(): "test-token", ApiKey(): "test-key"}))

    def restore(self) -> None:
        pass
