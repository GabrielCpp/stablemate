"""A whole store as one plain JSON document: its shape, the export and the import plan."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from saddlebag import totp
from saddlebag.models import VALUE_FIELDS, Secret, validate_meta_key, validate_name, validate_var
from saddlebag.store import SecretStore, StoreUnavailable

FORMAT = "saddlebag-export"
VERSION = 1
SUFFIX = ".saddlebag.json"

_KEYS = ("name", "username", "description", "var", "tags", "metadata", "values")


class DocumentError(ValueError):
    """The document cannot be loaded. The message names every problem and never a value."""


class ImportInterrupted(RuntimeError):
    """The store failed after the first write. The message names what was imported before it."""


@dataclass(frozen=True)
class ExportedSecret:
    """One secret's record and its values; an empty string means no value."""

    secret: Secret
    values: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        record = self.secret.to_dict()
        del record["fields"]
        record["values"] = {name: self.values.get(name, "") for name in VALUE_FIELDS}
        return record


def export(store: SecretStore) -> dict[str, object]:
    """Every secret of ``store`` with its values, as the document's JSON object."""
    secrets: list[ExportedSecret] = []
    for name in store.names():
        secret = store.get(name)
        if secret is None:
            continue
        values = {key: (store.value(name, key) or "") if key in secret.fields else "" for key in VALUE_FIELDS}
        secrets.append(ExportedSecret(secret, values))
    return document(secrets)


def document(secrets: list[ExportedSecret]) -> dict[str, object]:
    """The document's JSON object, secrets in name order."""
    ordered = sorted(secrets, key=lambda item: item.secret.name)
    return {"format": FORMAT, "version": VERSION, "secrets": [item.to_dict() for item in ordered]}


def render(payload: object) -> str:
    """The document's text: two-space indent, one trailing newline."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def count(payload: object) -> int:
    """How many secrets the document's JSON object holds."""
    secrets = payload.get("secrets") if isinstance(payload, dict) else None
    return len(secrets) if isinstance(secrets, list) else 0


def _optional_text(entry: dict[str, Any], key: str, where: str, problems: list[str]) -> str | None:
    value = entry.get(key)
    if value is not None and not isinstance(value, str):
        problems.append(f"{where}: {key} must be a string or null")
        return None
    return value


def _tags(raw: Any, where: str, problems: list[str]) -> frozenset[tuple[str, str]]:
    if not isinstance(raw, list):
        problems.append(f"{where}: tags must be a list of [key, value] pairs")
        return frozenset()
    pairs: set[tuple[str, str]] = set()
    for pair in raw:
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(part, str) and part.strip() for part in pair)):
            problems.append(f"{where}: tags must be a list of [key, value] pairs of non-empty strings")
            continue
        pairs.add((pair[0], pair[1]))
    return frozenset(pairs)


def _metadata(raw: Any, where: str, problems: list[str]) -> dict[str, str]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
        problems.append(f"{where}: metadata must be an object of strings")
        return {}
    for key in raw:
        try:
            validate_meta_key(key)
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
    return dict(raw)


def _values(raw: Any, where: str, problems: list[str]) -> dict[str, str]:
    if not isinstance(raw, dict):
        problems.append(f"{where}: values must be an object with {' and '.join(VALUE_FIELDS)}")
        return {}
    values: dict[str, str] = {}
    for key, value in raw.items():
        if key not in VALUE_FIELDS:
            problems.append(f"{where}: unknown value {key!r}, expected {' or '.join(VALUE_FIELDS)}")
        elif not isinstance(value, str):
            problems.append(f"{where}: values.{key} must be a string")
        else:
            values[key] = value
    seed = values.get("totp")
    if seed:
        try:
            totp.decode_seed(seed)
        except totp.SeedError as exc:
            problems.append(f"{where}: {exc}")
    return values


def _entry(entry: Any, index: int, problems: list[str]) -> ExportedSecret | None:
    where = f"secret {index + 1}"
    if not isinstance(entry, dict):
        problems.append(f"{where}: must be an object")
        return None
    name = entry.get("name")
    if not isinstance(name, str):
        problems.append(f"{where}: name must be a string")
        return None
    where = f"secret {name!r}"
    before = len(problems)
    try:
        validate_name(name)
    except ValueError as exc:
        problems.append(f"{where}: {exc}")
    unknown = sorted(str(key) for key in entry if key not in _KEYS)
    if unknown:
        problems.append(f"{where}: unknown keys {', '.join(unknown)}")
    var = _optional_text(entry, "var", where, problems)
    if var is not None:
        try:
            validate_var(var)
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
    secret = Secret(
        name=name,
        username=_optional_text(entry, "username", where, problems),
        description=_optional_text(entry, "description", where, problems),
        var=var,
        tags=_tags(entry.get("tags", []), where, problems),
        metadata=_metadata(entry.get("metadata", {}), where, problems),
    )
    values = _values(entry.get("values", {}), where, problems)
    return None if len(problems) > before else ExportedSecret(secret, values)


def read(payload: object) -> list[ExportedSecret]:
    """The document's secrets, or a DocumentError naming every problem in it."""
    secrets, problems = _parse(payload)
    if problems:
        raise DocumentError("; ".join(problems))
    return secrets


def _parse(payload: Any) -> tuple[list[ExportedSecret], list[str]]:
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise DocumentError(f"not a saddlebag export: the top-level object needs \"format\": \"{FORMAT}\"")
    version = payload.get("version")
    if version != VERSION:
        raise DocumentError(f"unsupported export version {version!r}: this saddlebag reads version {VERSION}")
    raw = payload.get("secrets")
    if not isinstance(raw, list):
        raise DocumentError("the export has no \"secrets\" list")
    problems: list[str] = []
    secrets = [item for index, entry in enumerate(raw) if (item := _entry(entry, index, problems)) is not None]
    seen: set[str] = set()
    for item in secrets:
        if item.secret.name in seen:
            problems.append(f"secret {item.secret.name!r}: appears twice")
        seen.add(item.secret.name)
    return secrets, problems


def load(store: SecretStore, payload: object, *, replace: bool = False) -> list[str]:
    """Write the document's secrets into ``store`` once all of them pass, and return their names."""
    secrets, problems = _parse(payload)
    existing = set(store.names())
    clashes = sorted({item.secret.name for item in secrets if item.secret.name in existing})
    if clashes and not replace:
        problems.append(f"already in the store: {', '.join(clashes)}. Pass --replace to overwrite them")
    if problems:
        raise DocumentError("; ".join(problems))
    written: list[str] = []
    for item in secrets:
        name = item.secret.name
        try:
            if name in existing:
                store.remove(name)
            store.create(item.secret)
            for key in VALUE_FIELDS:
                if item.values.get(key):
                    store.set_value(name, key, item.values[key])
        except Exception as exc:
            reason = str(exc) if isinstance(exc, StoreUnavailable) else type(exc).__name__
            done = ", ".join(written) or "none"
            raise ImportInterrupted(f"the store failed on {name} ({reason}); imported before it: {done}") from exc
        written.append(name)
    return written
