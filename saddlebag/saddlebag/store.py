"""Secret stores — where passwords actually live.

saddlebag never encrypts anything itself. It delegates to a store that already
does it properly:

1. the **OS keyring** (macOS Keychain, Windows Credential Manager, Linux Secret
   Service) whenever a real backend is present — the common case on a laptop,
   and zero configuration;
2. a **HashiCorp Vault** KV v2 mount otherwise — for containers, CI, and any
   host with no desktop session.

If neither is available saddlebag refuses to run rather than degrading to
plaintext. ``SADDLEBAG_BACKEND=keyring|vault`` overrides the autodetection.

Scoping note: the portable cross-OS keyring contract is exactly
``(service, username, password)`` — there is no collection or file parameter in
it. Linux's Secret Service backend exposes a ``preferred_collection`` hook, but
it takes a D-Bus path and has no macOS/Windows equivalent, so using it would be
a Linux-only path that silently no-ops elsewhere. Saddlebag therefore scopes its
secrets with a dedicated **service name** (:data:`SERVICE`), which is a real
isolation boundary: a lookup under any other service name returns ``None``.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

#: Namespace for every secret saddlebag writes to the OS keyring.
SERVICE = "saddlebag"

#: Default KV v2 mount and path prefix used by the Vault store.
VAULT_MOUNT = "secret"
VAULT_PREFIX = "saddlebag"

#: The KV field a Vault secret's value is written under, and the field earlier
#: versions used — read for back-compat, never written.
VALUE_FIELD = "value"
LEGACY_VALUE_FIELD = "password"


class StoreUnavailableError(RuntimeError):
    """No secret store could be opened. Carries operator-facing remediation."""


@runtime_checkable
class SecretStore(Protocol):
    """Put/get/delete a string-keyed secret.

    The key is whatever the caller says it is: a credential's password lives under
    ``<project>/<cred-id>``, an environment's secret entry under
    ``<project>/<env-id>/<KEY>``. The store neither knows nor cares which — it is a
    namespaced string→secret map, and the parameter names below are historical.
    """

    name: str

    def put(self, credential_id: str, password: str) -> None: ...

    def get(self, credential_id: str) -> str | None: ...

    def delete(self, credential_id: str) -> None: ...


class KeyringStore:
    """Passwords in the OS keyring, namespaced under the ``saddlebag`` service."""

    name = "keyring"

    def __init__(self, service: str = SERVICE) -> None:
        self.service = service

    def put(self, credential_id: str, password: str) -> None:
        import keyring

        keyring.set_password(self.service, credential_id, password)

    def get(self, credential_id: str) -> str | None:
        import keyring

        return keyring.get_password(self.service, credential_id)

    def delete(self, credential_id: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(self.service, credential_id)
        except PasswordDeleteError:
            # Already absent — deletion is idempotent from the pool's point of view.
            pass


class VaultStore:
    """Secrets in a Vault KV v2 mount, one Vault secret per store key.

    Requires the ``vault`` extra (``pip install 'saddlebag[vault]'``) and the
    usual ``VAULT_ADDR`` / ``VAULT_TOKEN`` environment variables.

    The KV field is :data:`VALUE_FIELD`. It used to be ``password``, which was a
    lie the moment an environment's ``VITE_FIREBASE_API_KEY`` started living here;
    reads still fall back to the old field so a Vault written by an earlier
    saddlebag keeps resolving.
    """

    name = "vault"

    def __init__(self, mount: str = VAULT_MOUNT, prefix: str = VAULT_PREFIX) -> None:
        self.mount = mount
        self.prefix = prefix
        self._client = self._connect()

    @staticmethod
    def _connect():  # noqa: ANN205 - hvac client type is not imported at module scope
        try:
            import hvac
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on extras
            raise StoreUnavailableError(
                "the vault backend needs hvac: pip install 'saddlebag[vault]'"
            ) from exc

        addr = os.environ.get("VAULT_ADDR")
        if not addr:
            raise StoreUnavailableError("VAULT_ADDR is not set")
        client = hvac.Client(url=addr, token=os.environ.get("VAULT_TOKEN"))
        if not client.is_authenticated():
            raise StoreUnavailableError("Vault rejected the token in VAULT_TOKEN")
        return client

    def _path(self, credential_id: str) -> str:
        return f"{self.prefix}/{credential_id}"

    def put(self, credential_id: str, password: str) -> None:
        self._client.secrets.kv.v2.create_or_update_secret(
            path=self._path(credential_id),
            secret={VALUE_FIELD: password},
            mount_point=self.mount,
        )

    def get(self, credential_id: str) -> str | None:
        import hvac

        try:
            resp = self._client.secrets.kv.v2.read_secret_version(
                path=self._path(credential_id),
                mount_point=self.mount,
                raise_on_deleted_version=True,
            )
        except hvac.exceptions.InvalidPath:
            return None
        data = resp["data"]["data"]
        if VALUE_FIELD in data:
            return data[VALUE_FIELD]
        return data.get(LEGACY_VALUE_FIELD)

    def delete(self, credential_id: str) -> None:
        self._client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=self._path(credential_id),
            mount_point=self.mount,
        )


def keyring_available() -> bool:
    """True when a *real* OS keyring backend is present.

    ``keyring`` does not raise when nothing is available — it silently selects
    ``fail.Keyring``, whose methods raise only on use. Probing the selected
    backend's type is therefore the reliable check, not a try/except around a
    write.
    """
    try:
        import keyring
        import keyring.backends.fail
    except ModuleNotFoundError:  # pragma: no cover - keyring is a hard dependency
        return False
    return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)


def vault_configured() -> bool:
    """True when the environment points at a Vault server."""
    return bool(os.environ.get("VAULT_ADDR"))


def open_store(backend: str | None = None) -> SecretStore:
    """Open the secret store, preferring the OS keyring, falling back to Vault.

    Raises :class:`StoreUnavailableError` — never degrades to plaintext — when
    no store is available.
    """
    backend = backend or os.environ.get("SADDLEBAG_BACKEND")

    if backend == "keyring":
        if not keyring_available():
            raise StoreUnavailableError(
                "SADDLEBAG_BACKEND=keyring but no OS keyring backend is available"
            )
        return KeyringStore()
    if backend == "vault":
        return VaultStore()
    if backend:
        raise StoreUnavailableError(
            f"unknown SADDLEBAG_BACKEND={backend!r} (expected 'keyring' or 'vault')"
        )

    if keyring_available():
        return KeyringStore()
    if vault_configured():
        return VaultStore()

    raise StoreUnavailableError(
        "no secret store available: saddlebag found no OS keyring backend "
        "(is this a headless session?) and VAULT_ADDR is unset.\n"
        "  - on a desktop: start a keyring daemon, or unlock your login keyring\n"
        "  - in CI or a container: set VAULT_ADDR and VAULT_TOKEN, and install "
        "the vault extra: pip install 'saddlebag[vault]'"
    )
