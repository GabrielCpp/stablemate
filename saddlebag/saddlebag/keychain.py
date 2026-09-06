"""Reading a secret that already lives in the OS keychain, under somebody else's name.

:mod:`saddlebag.store` writes secrets under saddlebag's own service name, which is
what makes ``add`` self-contained. But a secret does not always arrive that way. A
machine account's password is often put into the keychain by the person who created
it — with ``secret-tool``, ``security add-generic-password``, or the desktop's own
keychain app — long before any pool exists, and under attributes that describe the
account rather than the tool that reads it.

Copying it into saddlebag's namespace to make it readable is the wrong move. It
leaves two copies of one password on the machine, and the copy is the one that goes
stale silently: the operator rotates the credential where they created it, and every
run keeps presenting the old value until an account locks. So saddlebag reads the
original in place. The pool records *where* the secret is — a set of attributes,
which is metadata and safe to print — and resolves it on each use.

**Attributes, not a path.** The Secret Service addresses an item by an arbitrary
attribute map, and a search matches any item whose attributes are a superset of the
query. That is why a query has to be specific enough to identify one item:
``service=github account=bot`` matches both the password and the TOTP seed of the
same account, and picking whichever came back first would type a seed into a password
field. Ambiguity is an error here for the same reason it is in
:func:`saddlebag.browser.select_target`.

**Linux only, and it says so.** The cross-OS keyring contract is
``(service, username)`` and has no attribute map in it, so there is nothing portable
to implement this against; on macOS and Windows the reference below raises rather
than silently resolving to a different item than the operator meant.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from typing import Any

from saddlebag.models import Credential, KeychainRef
from saddlebag.store import SecretStore

#: Attributes the Secret Service maintains itself. Excluded from an item's reported
#: attributes so `saddlebag link` can be re-run from what `saddlebag show` prints.
MANAGED_ATTRIBUTES: frozenset[str] = frozenset({"xdg:schema"})


class KeychainError(RuntimeError):
    """A referenced keychain item could not be read. Carries operator-facing detail."""


def parse_attributes(pairs: Sequence[str]) -> dict[str, str]:
    """``["service=github", "type=password"]`` → a query.

    Splits on the first ``=`` only, so a value may contain one. An empty name or a
    pair with no ``=`` is rejected: an attribute that silently became ``""`` would
    widen the query rather than narrow it, and a widened query is how the wrong item
    gets read.
    """
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
    # Imported here rather than at module scope, and this is the one place in the
    # package that earns the exception: SecretStorage binds to D-Bus and does not
    # install on macOS or Windows at all. At module scope it would take the whole
    # CLI down on import for every user who has no Secret Service to talk to —
    # including the ones whose secrets are all in saddlebag's own store and who
    # never reach this function.
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
    """The secret behind a reference.

    Raises rather than returning ``None``: every caller of this treats a missing
    secret as fatal, and the reason it is missing — no such item, several items, a
    locked keyring — is the whole diagnosis. Collapsing those three into ``None``
    moves the operator's next question out of the error and into a support thread.
    """
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
    """The attributes of the one item a query matches, minus the ones the service owns.

    What ``link --probe`` prints so an operator can see they have addressed the item
    they meant, before a run depends on it.
    """
    attributes = parse_attributes(list(pairs))
    items = _search(attributes)
    if len(items) != 1:
        raise KeychainError(f"{len(items)} keychain items match {_describe(attributes)}")
    found: dict[str, str] = items[0].get_attributes()
    return {k: v for k, v in found.items() if k not in MANAGED_ATTRIBUTES}


def password_for(cred: Credential, store: SecretStore) -> str | None:
    """A credential's password, from wherever that credential says it lives.

    The reference wins when there is one. A credential cannot hold both — ``link``
    refuses to shadow a stored password — so this is a choice between two sources,
    never a fallback chain that could resolve to a stale copy.
    """
    if cred.password_ref is not None:
        return lookup(cred.password_ref)
    return store.get(cred.store_key)


def seed_for(cred: Credential, store: SecretStore) -> str | None:
    """A credential's TOTP enrolment seed. See :func:`password_for`."""
    if cred.totp_ref is not None:
        return lookup(cred.totp_ref)
    return store.get(cred.totp_store_key)
