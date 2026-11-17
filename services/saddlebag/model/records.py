"""The secret a person keeps: what the record says and which values stand behind it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

Pairs = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SecretRecord:
    """A named secret. The record says which values exist and the vault holds them."""

    name: str
    username: str | None = None
    description: str | None = None
    var: str | None = None
    tags: Pairs = ()
    metadata: Pairs = ()
    password: str | None = None
    totp: str | None = None

    source: ClassVar[tuple[str, ...]] = ("saddlebag/saddlebag/models.py::Secret", "saddlebag/saddlebag/keyring_store.py::KeyringStore",
                                         "saddlebag/saddlebag/catalogue.py::Catalogue")

    @property
    def fields(self) -> list[str]:
        return [field for field in ("password", "totp") if getattr(self, field) is not None]

    @property
    def tag_pairs(self) -> list[list[str]]:
        return [list(pair) for pair in self.tags]

    @property
    def metadata_map(self) -> dict[str, str]:
        return dict(sorted(self.metadata))

    def value(self, field: str) -> str | None:
        if field == "username":
            return self.username
        if field.startswith("meta."):
            return dict(self.metadata).get(field[5:])
        return getattr(self, field, None)

    def __str__(self) -> str:
        return f"{self.name} [{','.join(self.fields)}]"
