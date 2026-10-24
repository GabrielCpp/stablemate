"""The shelf every verb talks to: records and values, behind one contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from saddlebag.models import Secret, Tag


class StoreUnavailable(RuntimeError):
    """The store cannot be reached. The message says what the operator does next."""


@dataclass(frozen=True)
class StoreHealth:
    """What a store reports about itself: reachability, catalogue drift and unclaimed items."""

    backend: str
    reachable: bool
    missing_items: tuple[str, ...] = ()
    orphan_items: tuple[str, ...] | None = None


class SecretStore(Protocol):
    """Where the secrets live."""

    def health(self) -> StoreHealth: ...
    def names(self) -> list[str]: ...
    def get(self, name: str) -> Secret | None: ...
    def create(self, secret: Secret) -> None: ...
    def set_value(self, name: str, field: str, value: str) -> None: ...
    def unset_value(self, name: str, field: str) -> None: ...
    def remove(self, name: str) -> None: ...
    def value(self, name: str, field: str) -> str | None: ...
    def retag(self, name: str, tags: frozenset[Tag]) -> None: ...
