"""The environment manifest — a checkable-in YAML rendering of an environment.

The pool database is local and unsynced. For credentials that asymmetry is
tolerable; for *configuration* it would defeat the purpose, because an environment
that cannot leave the laptop it was defined on has not packaged anything. So the
thing that travels is not the database but this manifest: every key, its kind, its
note, its ``required`` flag, the render target and format, and — for ``config``
entries — the value itself.

It holds **no secret values**, by construction. A ``secret`` entry appears as a
declaration that a secret is required under that key, never as the secret; the
value stays in the store. The two halves then meet cleanly on a fresh host: the
manifest carries the configuration, the store carries the secrets, and
``env doctor`` names exactly which secrets are still missing.

:func:`load` enforces the no-secrets rule at the file boundary — a hand-edited
manifest that puts a ``value:`` on a ``secret`` entry is rejected, not imported.
That is the same fence as the database's ``CHECK`` constraint, at the other end of
the pipe.

This subsumes ``.env.example`` rather than living beside it: the example file is a
key list with no kinds, no notes, no required flags, no target and no values, and
the manifest is a strict superset.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import (
    FORMATS,
    KIND_CONFIG,
    KIND_CREDENTIAL_REF,
    KIND_PENDING,
    Environment,
    EnvironmentEntry,
    parse_cred_ref,
)


class ManifestError(ValueError):
    """A manifest is malformed, or carries something it must never carry."""


@dataclass(frozen=True)
class Manifest:
    """A parsed manifest: an environment's metadata plus its ordered entries."""

    name: str
    env: str
    target: str | None = None
    format: str = "dotenv"
    description: str | None = None
    entries: tuple[EnvironmentEntry, ...] = ()


def to_dict(environment: Environment) -> dict[str, Any]:
    """The manifest form of an environment. Never contains a secret value.

    Optional fields are omitted when they carry nothing, so a simple environment
    exports as a short, readable, reviewable file rather than a wall of nulls.
    """
    data: dict[str, Any] = {"name": environment.name, "env": environment.env}
    if environment.target:
        data["target"] = environment.target
    data["format"] = environment.format
    if environment.description:
        data["description"] = environment.description

    entries: list[dict[str, Any]] = []
    for entry in environment.entries:
        item: dict[str, Any] = {"key": entry.key, "kind": entry.kind}
        # `value` is populated for config entries only — the model guarantees every
        # other kind holds None, so this cannot leak even if it wanted to.
        if entry.kind == KIND_CONFIG:
            item["value"] = entry.value
        if entry.cred_ref:
            item["from"] = entry.cred_ref
        if entry.note:
            item["note"] = entry.note
        if not entry.required:
            item["required"] = False
        entries.append(item)
    data["entries"] = entries
    return data


def dumps(environment: Environment) -> str:
    """Serialise an environment as manifest YAML, in render order."""
    return yaml.safe_dump(to_dict(environment), sort_keys=False, allow_unicode=True)


def _entry_from(item: Any, position: int) -> EnvironmentEntry:
    if not isinstance(item, dict):
        raise ManifestError(f"entry {position} is not a mapping")
    key = item.get("key")
    if not key or not isinstance(key, str):
        raise ManifestError(f"entry {position} has no key")

    kind = item.get("kind", KIND_PENDING)
    value = item.get("value")
    cred_ref = item.get("from")

    if kind != KIND_CONFIG and value is not None:
        # The whole point of the manifest is that it is safe to commit. A value on
        # any other kind means someone pasted a secret into a file bound for git.
        raise ManifestError(
            f"{key}: a {kind} entry must not carry a value — its value belongs in "
            "the secret store, not in a manifest"
        )
    if kind == KIND_CONFIG and value is None:
        raise ManifestError(f"{key}: a config entry needs a value")
    if kind == KIND_CREDENTIAL_REF and not cred_ref:
        raise ManifestError(f"{key}: a credential-ref entry needs a 'from:' reference")
    if kind == KIND_CREDENTIAL_REF:
        try:
            parse_cred_ref(str(cred_ref))
        except ValueError as exc:
            raise ManifestError(f"{key}: {exc}") from exc

    try:
        return EnvironmentEntry(
            key=key,
            kind=kind,
            # YAML happily reads `value: 9099` as an int; a .env holds text.
            value=str(value) if value is not None else None,
            cred_ref=str(cred_ref) if cred_ref is not None else None,
            required=bool(item.get("required", True)),
            note=item.get("note"),
            position=position,
        )
    except ValueError as exc:
        raise ManifestError(f"{key}: {exc}") from exc


def loads(text: str) -> Manifest:
    """Parse manifest YAML. Raises :class:`ManifestError` on anything malformed."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestError(f"not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError("a manifest must be a YAML mapping")
    name = data.get("name")
    env = data.get("env")
    if not name:
        raise ManifestError("a manifest needs a name")
    if not env:
        raise ManifestError("a manifest needs an env (e.g. local, staging)")

    fmt = data.get("format", "dotenv")
    if fmt not in FORMATS:
        raise ManifestError(f"unknown format {fmt!r} (expected one of {', '.join(FORMATS)})")

    raw_entries = data.get("entries") or []
    if not isinstance(raw_entries, list):
        raise ManifestError("'entries' must be a list")

    entries = tuple(
        _entry_from(item, position) for position, item in enumerate(raw_entries, start=1)
    )
    seen = [e.key for e in entries]
    duplicates = {k for k in seen if seen.count(k) > 1}
    if duplicates:
        raise ManifestError(f"duplicate keys: {', '.join(sorted(duplicates))}")

    return Manifest(
        name=str(name),
        env=str(env),
        target=data.get("target"),
        format=fmt,
        description=data.get("description"),
        entries=entries,
    )


def load(path: Path | str) -> Manifest:
    """Read and parse a manifest file."""
    return loads(Path(path).read_text(encoding="utf-8"))


def is_manifest_path(path: Path | str) -> bool:
    """Whether ``--from PATH`` names a manifest or a plain ``.env``-shaped key list.

    Dispatch on the suffix, not on a sniff of the contents: ``env import`` decides
    between "reconstitute this whole environment" and "take these key names and
    nothing else", and a caller must be able to predict which one they are getting.
    """
    return Path(path).suffix.lower() in (".yaml", ".yml")
