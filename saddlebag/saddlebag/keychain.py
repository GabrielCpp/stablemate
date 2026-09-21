"""Reading a secret that already lives in the OS keychain, under somebody else's name."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from typing import Any

from saddlebag.models import Credential, KeychainRef
from saddlebag.store import SecretStore

MANAGED_ATTRIBUTES: frozenset[str] = frozenset({"xdg:schema"})


class KeychainError(RuntimeError):
    """A referenced keychain item could not be read."""


def parse_attributes(pairs: Sequence[str]) -> dict[str, str]:
    """``["service=github", "type=password"]`` → a query."""
    attributes: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name:
            raise KeychainError(f"expected an attribute as name=value, got {pair!r}")
        attributes[name] = value
    if not attributes:
        raise KeychainError("a keychain reference needs at least one attribute")
    return attributes


def _search(attributes: dict[str, str]) -> list[Any]:
    if sys.platform != "linux":  # pragma: no cover - platform-specific
        raise KeychainError(
            "reading a keychain item by attributes is implemented for the Secret "
            f"Service (Linux) only; this is {sys.platform}. Store the secret under "
            "saddlebag's own service instead: saddlebag add --password-stdin"
        )
    import secretstorage

    try:
        connection = secretstorage.dbus_init()
        return list(secretstorage.search_items(connection, attributes))
    except secretstorage.SecretServiceNotAvailableException as exc:
        raise KeychainError(
            "no Secret Service is running — a desktop session's keyring daemon "
            f"provides it ({exc})"
        ) from exc


def _describe(attributes: dict[str, str]) -> str:
    return " ".join(f"{name}={value}" for name, value in sorted(attributes.items()))


def lookup(ref: KeychainRef) -> str:
    """The secret behind a reference."""
    attributes = ref.as_dict()
    items = _search(attributes)
    if not items:
        raise KeychainError(
            f"no keychain item matches {_describe(attributes)}. "
            "List what is there with: secret-tool search <name> <value>"
        )
    if len(items) > 1:
        labels = "\n".join(f"  - {item.get_label()}" for item in items)
        raise KeychainError(
            f"{len(items)} keychain items match {_describe(attributes)}; add an "
            f"attribute so the reference names exactly one:\n{labels}"
        )
    item = items[0]
    if item.is_locked():
        raise KeychainError(
            f"the keychain item matching {_describe(attributes)} is locked; "
            "unlock the keyring and try again"
        )
    secret: bytes = item.get_secret()
    return secret.decode("utf-8")


def item_attributes(pairs: Iterable[str]) -> dict[str, str]:
    """The attributes of the one item a query matches, minus the ones the service owns."""
    attributes = parse_attributes(list(pairs))
    items = _search(attributes)
    if len(items) != 1:
        raise KeychainError(f"{len(items)} keychain items match {_describe(attributes)}")
    found: dict[str, str] = items[0].get_attributes()
    return {k: v for k, v in found.items() if k not in MANAGED_ATTRIBUTES}


def password_for(cred: Credential, store: SecretStore) -> str | None:
    """A credential's password, from wherever that credential says it lives."""
    if cred.password_ref is not None:
        return lookup(cred.password_ref)
    return store.get(cred.store_key)


def seed_for(cred: Credential, store: SecretStore) -> str | None:
    """A credential's TOTP enrolment seed."""
    if cred.totp_ref is not None:
        return lookup(cred.totp_ref)
    return store.get(cred.totp_store_key)
