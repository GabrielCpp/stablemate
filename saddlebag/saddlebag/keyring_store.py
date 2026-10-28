"""The OS keyring door and the shelf behind it: values in the keyring, records in a catalogue."""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace

import keyring
import keyring.backends.SecretService
import keyring.errors
from keyring.backend import KeyringBackend

from saddlebag.catalogue import Catalogue
from saddlebag.models import META_PREFIX, VALUE_FIELDS, Secret, Tag
from saddlebag.store import StoreHealth, StoreUnavailable

SERVICE = "stablemate-saddlebag"
SECRET_SERVICE_BACKEND = "keyring.backends.SecretService.Keyring"
MACOS_BACKEND = "keyring.backends.macOS.Keyring"
ALLOWED_BACKENDS = frozenset({SECRET_SERVICE_BACKEND, MACOS_BACKEND})

LOCKED = (
    "the OS keyring is locked. Unlock it (desktop: answer the prompt; SSH: pipe your login password to "
    "gnome-keyring-daemon --unlock), or start a daemon with saddlebag serve and set SADDLEBAG_BACKEND=daemon."
)
ABSENT = (
    "no OS keyring on this session: no Secret Service on the session bus and no Keychain. Run saddlebag from a "
    "desktop session, or start a daemon with saddlebag serve and set SADDLEBAG_BACKEND=daemon."
)
DISTRUSTED = (
    "the Keychain refused this interpreter ({interpreter}) for {name}. Choose Always Allow in the Keychain "
    "prompt, or pre-authorise it with security add-generic-password -T {interpreter} -U -s stablemate-saddlebag "
    "-a {account}."
)
REFUSED = "the OS keyring refused {name}: {error}"


def _kind(backend: KeyringBackend) -> str:
    return f"{type(backend).__module__}.{type(backend).__name__}"


def open_door() -> KeyringBackend:
    """The OS keyring, or StoreUnavailable saying whether it is absent, locked or distrustful."""
    backend = keyring.get_keyring()
    if _kind(backend) not in ALLOWED_BACKENDS:
        raise StoreUnavailable(ABSENT)
    if isinstance(backend, keyring.backends.SecretService.Keyring):
        _guarded(backend.get_preferred_collection, "the keyring")
    return backend


def _guarded[T](fn: Callable[[], T], name: str) -> T:
    try:
        return fn()
    except keyring.errors.KeyringLocked as exc:
        raise StoreUnavailable(LOCKED) from exc
    except (keyring.errors.NoKeyringError, keyring.errors.InitError) as exc:
        raise StoreUnavailable(ABSENT) from exc
    except keyring.errors.KeyringError as exc:
        if sys.platform != "darwin":
            raise StoreUnavailable(REFUSED.format(name=name, error=exc)) from exc
        raise StoreUnavailable(DISTRUSTED.format(interpreter=sys.executable, name=name, account=name)) from exc


def secret_service_accounts() -> list[str] | None:
    """Every account the Secret Service holds under SERVICE, or None when this keyring cannot list them."""
    backend = keyring.get_keyring()
    if not isinstance(backend, keyring.backends.SecretService.Keyring):
        return None

    def listing() -> list[str]:
        collection = backend.get_preferred_collection()
        with contextlib.closing(collection.connection):
            items = collection.search_items({"service": SERVICE})
            names = (item.get_attributes().get("username") for item in items)
            return sorted(name for name in names if name is not None)

    return _guarded(listing, "doctor")


def _account(name: str, field: str) -> str:
    return f"{name}/{field}"


class KeyringStore:
    """A SecretStore with values in the OS keyring and records in a Catalogue."""

    def __init__(
        self,
        catalogue: Catalogue,
        backend: KeyringBackend,
        accounts: Callable[[], list[str] | None] = lambda: None,
    ) -> None:
        self._catalogue = catalogue
        self._backend = backend
        self._accounts = accounts

    def _record(self, name: str) -> Secret:
        secret = self._catalogue.get(name)
        if secret is None:
            raise StoreUnavailable(f"no such secret: {name}")
        return secret

    def _delete(self, name: str, field: str) -> None:
        account = _account(name, field)

        def delete() -> None:
            try:
                self._backend.delete_password(SERVICE, account)
            except keyring.errors.PasswordDeleteError:
                return

        _guarded(delete, account)

    def health(self) -> StoreHealth:
        claimed: set[str] = set()
        missing: list[str] = []
        for name in self._catalogue.names():
            record = self._catalogue.get(name)
            if record is None:
                continue
            for field in sorted(record.fields):
                account = _account(name, field)
                claimed.add(account)
                if _guarded(lambda account=account: self._backend.get_password(SERVICE, account), account) is None:
                    missing.append(account)
        held = self._accounts()
        orphans = None if held is None else tuple(sorted(set(held) - claimed))
        interpreter = sys.executable if _kind(self._backend) == MACOS_BACKEND else None
        return StoreHealth("keyring", True, tuple(missing), orphans, interpreter)

    def names(self) -> list[str]:
        return self._catalogue.names()

    def get(self, name: str) -> Secret | None:
        return self._catalogue.get(name)

    def create(self, secret: Secret) -> None:
        self._catalogue.put(replace(secret, fields=frozenset()))

    def set_value(self, name: str, field: str, value: str) -> None:
        secret = self._record(name)
        account = _account(name, field)
        _guarded(lambda: self._backend.set_password(SERVICE, account, value), account)
        self._catalogue.put(replace(secret, fields=secret.fields | {field}))

    def unset_value(self, name: str, field: str) -> None:
        secret = self._record(name)
        self._delete(name, field)
        self._catalogue.put(replace(secret, fields=secret.fields - {field}))

    def remove(self, name: str) -> None:
        for field in VALUE_FIELDS:
            self._delete(name, field)
        self._catalogue.drop(name)

    def value(self, name: str, field: str) -> str | None:
        if field == "username":
            secret = self._catalogue.get(name)
            return secret.username if secret else None
        if field.startswith(META_PREFIX):
            secret = self._catalogue.get(name)
            return secret.metadata.get(field[len(META_PREFIX) :]) if secret else None
        account = _account(name, field)
        return _guarded(lambda: self._backend.get_password(SERVICE, account), account)

    def retag(self, name: str, tags: frozenset[Tag]) -> None:
        self._catalogue.put(replace(self._record(name), tags=tags))

    def set_metadata(self, name: str, metadata: Mapping[str, str]) -> None:
        self._catalogue.put(replace(self._record(name), metadata=dict(metadata)))
