"""The Vault KV v2 store: values in data, metadata in custom_metadata."""

from __future__ import annotations

import json
from typing import Any, Protocol

import hvac
from hvac.exceptions import InvalidPath

from saddlebag.models import VALUE_FIELDS, Secret, Tag


class VaultError(RuntimeError):
    """Vault could not be reached or refused the token."""


class SecretStore(Protocol):
    """Where the secrets live."""

    def is_authenticated(self) -> bool: ...
    def names(self) -> list[str]: ...
    def get(self, name: str) -> Secret | None: ...
    def create(self, secret: Secret) -> None: ...
    def set_value(self, name: str, field: str, value: str) -> None: ...
    def unset_value(self, name: str, field: str) -> None: ...
    def remove(self, name: str) -> None: ...
    def value(self, name: str, field: str) -> str | None: ...
    def retag(self, name: str, tags: frozenset[Tag]) -> None: ...


class VaultStore:
    """A :class:`SecretStore` over one KV v2 mount."""

    def __init__(self, addr: str, token: str, mount: str = "secret", prefix: str = "saddlebag") -> None:
        self.mount = mount
        self.prefix = prefix
        self._client: Any = hvac.Client(url=addr, token=token)
        if not self._client.is_authenticated():
            raise VaultError(f"Vault at {addr} rejected the token")

    def _path(self, name: str) -> str:
        return f"{self.prefix}/{name}"

    def _kv(self) -> Any:
        return self._client.secrets.kv.v2

    def _data(self, name: str) -> dict[str, str]:
        try:
            response = self._kv().read_secret_version(
                path=self._path(name), mount_point=self.mount, raise_on_deleted_version=True
            )
        except InvalidPath:
            return {}
        return dict(response["data"]["data"])

    def _write_metadata(self, secret: Secret) -> None:
        custom = {
            key: value
            for key, value in (
                ("username", secret.username),
                ("description", secret.description),
                ("var", secret.var),
            )
            if value is not None
        }
        custom["tags"] = json.dumps(sorted(secret.tags))
        self._kv().update_metadata(path=self._path(secret.name), mount_point=self.mount, custom_metadata=custom)

    def is_authenticated(self) -> bool:
        return bool(self._client.is_authenticated())

    def names(self) -> list[str]:
        try:
            response = self._kv().list_secrets(path=self.prefix, mount_point=self.mount)
        except InvalidPath:
            return []
        return sorted(key for key in response["data"]["keys"] if not key.endswith("/"))

    def get(self, name: str) -> Secret | None:
        try:
            response = self._kv().read_secret_metadata(path=self._path(name), mount_point=self.mount)
        except InvalidPath:
            return None
        custom = response["data"].get("custom_metadata") or {}
        data = self._data(name)
        return Secret(
            name=name,
            username=custom.get("username"),
            description=custom.get("description"),
            var=custom.get("var"),
            tags=frozenset((k, v) for k, v in json.loads(custom.get("tags", "[]"))),
            fields=frozenset(key for key in VALUE_FIELDS if data.get(key)),
        )

    def create(self, secret: Secret) -> None:
        self._write_metadata(secret)

    def set_value(self, name: str, field: str, value: str) -> None:
        data = self._data(name)
        data[field] = value
        self._kv().create_or_update_secret(path=self._path(name), secret=data, mount_point=self.mount)

    def unset_value(self, name: str, field: str) -> None:
        data = self._data(name)
        if field not in data:
            return
        del data[field]
        self._kv().create_or_update_secret(path=self._path(name), secret=data, mount_point=self.mount)

    def remove(self, name: str) -> None:
        self._kv().delete_metadata_and_all_versions(path=self._path(name), mount_point=self.mount)

    def value(self, name: str, field: str) -> str | None:
        if field == "username":
            secret = self.get(name)
            return secret.username if secret else None
        return self._data(name).get(field) or None

    def retag(self, name: str, tags: frozenset[Tag]) -> None:
        secret = self.get(name)
        if secret is None:
            raise VaultError(f"no such secret: {name}")
        self._write_metadata(Secret(name, secret.username, secret.description, secret.var, tags))
