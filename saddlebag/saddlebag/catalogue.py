"""The keyring shelf's records, in one owner-only JSON file."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import platformdirs

from saddlebag.models import Secret
from saddlebag.store import StoreUnavailable

VERSION = 1


class Catalogue:
    """The keyring shelf's records, in one owner-only JSON file. It serialises Secret and nothing else."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def default(cls) -> Catalogue:
        """The catalogue under the stablemate state directory."""
        return cls(Path(platformdirs.user_state_dir("stablemate")) / "saddlebag" / "catalogue.json")

    def _load(self) -> dict[str, Secret]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise StoreUnavailable(f"cannot read the catalogue {self.path}: {exc.strerror or exc}") from exc
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("version") != VERSION:
                raise ValueError("unsupported version")
            return {secret.name: secret for secret in map(_secret, payload["secrets"])}
        except (ValueError, KeyError, TypeError) as exc:
            raise StoreUnavailable(f"the catalogue {self.path} is not a version {VERSION} catalogue: fix or remove it") from exc

    def _save(self, secrets: dict[str, Secret]) -> None:
        parent = self.path.parent
        created = not parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if created:
            parent.chmod(0o700)
        payload = json.dumps({"version": VERSION, "secrets": [secrets[name].to_dict() for name in sorted(secrets)]}, indent=2)
        temp = parent / f".{self.path.name}.{os.getpid()}.tmp"
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            os.replace(temp, self.path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def names(self) -> list[str]:
        """The record names, sorted."""
        return sorted(self._load())

    def get(self, name: str) -> Secret | None:
        """The record called ``name``, or None."""
        return self._load().get(name)

    def put(self, secret: Secret) -> None:
        """Insert or replace a record, then save."""
        secrets = self._load()
        secrets[secret.name] = secret
        self._save(secrets)

    def drop(self, name: str) -> None:
        """Forget a record, then save."""
        secrets = self._load()
        secrets.pop(name, None)
        self._save(secrets)


_KEYS = frozenset({"name", "username", "description", "var", "tags", "fields"})


def _secret(entry: Any) -> Secret:
    if not isinstance(entry, dict) or set(entry) != _KEYS:
        raise ValueError("unexpected record keys")
    return Secret(
        name=entry["name"],
        username=entry["username"],
        description=entry["description"],
        var=entry["var"],
        tags=frozenset((key, value) for key, value in entry["tags"]),
        fields=frozenset(entry["fields"]),
    )
