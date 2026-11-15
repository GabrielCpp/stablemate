"""The gateway as a surface, over the client that reaches it."""

from __future__ import annotations

from ostler.book import Client, HttpSurface


class GatewayApi(HttpSurface):
    name = "gateway"

    def __init__(self, client: Client):
        super().__init__(client)

    def restore(self) -> None:
        pass
