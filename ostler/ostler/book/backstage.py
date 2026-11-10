"""What a service does behind its surface to arrange a state no route can write:
accounts, rows only SQL reaches, a resource landed from outside. A service
gives each environment the backstage that can reach it. An operation the place
does not allow raises `CannotArrange`, and what needed it is skipped."""

from __future__ import annotations

from typing import Any, Protocol


class CannotArrange(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Backstage(Protocol):
    def address(self, name: str) -> str: ...

    def sql(self, statements: str) -> str: ...

    def mint_many(self, specs: dict[str, tuple[str, tuple[str, ...], int, int]], tag: str) -> dict[str, Any]: ...

    def root_of(self, project_id: str) -> str: ...

    def seed_order(self, supplier_email: str, project_id: str, name: str, order: str, token: str, billable: int = 0) -> None: ...
