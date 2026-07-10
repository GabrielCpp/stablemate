"""Secret-store selection and the keyring adapter.

These tests never touch the real OS keyring. ``keyring`` is a hard dependency, so
it always imports; what varies is which backend it reports, and that is exactly
what saddlebag branches on.
"""

from __future__ import annotations

import sys
import types

import pytest

from saddlebag import store as store_mod
from saddlebag.store import (
    SERVICE,
    KeyringStore,
    SecretStore,
    StoreUnavailableError,
    keyring_available,
    open_store,
    vault_configured,
)


class _FakeKeyringModule(types.ModuleType):
    """Stands in for the ``keyring`` package, recording (service, user) pairs."""

    def __init__(self, backend: object) -> None:
        super().__init__("keyring")
        self.saved: dict[tuple[str, str], str] = {}
        self._backend = backend
        self.deleted: list[tuple[str, str]] = []

    def get_keyring(self) -> object:
        return self._backend

    def set_password(self, service: str, username: str, password: str) -> None:
        self.saved[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.saved.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self.saved:
            raise PasswordDeleteError("not found")
        del self.saved[(service, username)]
        self.deleted.append((service, username))


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch):
    """Install a fake ``keyring`` module with a working (non-fail) backend."""
    import keyring.backends.fail

    real_backend = object()  # anything that is not a fail.Keyring
    module = _FakeKeyringModule(real_backend)
    module.backends = keyring.backends  # so `import keyring.backends.fail` resolves
    monkeypatch.setitem(sys.modules, "keyring", module)
    return module


def test_keyring_store_scopes_secrets_by_service_name(fake_keyring):
    KeyringStore().put("cred-007", "hunter2")
    assert fake_keyring.saved == {(SERVICE, "cred-007"): "hunter2"}


def test_keyring_store_round_trips(fake_keyring):
    kr = KeyringStore()
    kr.put("cred-007", "hunter2")
    assert kr.get("cred-007") == "hunter2"


def test_keyring_store_isolates_other_services(fake_keyring):
    KeyringStore().put("cred-007", "hunter2")
    assert KeyringStore(service="other-app").get("cred-007") is None


def test_missing_secret_reads_as_none(fake_keyring):
    assert KeyringStore().get("cred-404") is None


def test_delete_is_idempotent(fake_keyring):
    kr = KeyringStore()
    kr.put("cred-007", "hunter2")
    kr.delete("cred-007")
    kr.delete("cred-007")  # must not raise
    assert kr.get("cred-007") is None


def test_keyring_store_satisfies_the_protocol():
    assert isinstance(KeyringStore(), SecretStore)


# -- availability probing ---------------------------------------------------


def test_a_null_backend_reads_as_unavailable(monkeypatch: pytest.MonkeyPatch):
    """`keyring` silently selects fail.Keyring when nothing is installed.

    It does not raise until a method is called, so type-probing the selected
    backend is the only reliable check.
    """
    import keyring
    import keyring.backends.fail

    monkeypatch.setattr(keyring, "get_keyring", lambda: keyring.backends.fail.Keyring())
    assert keyring_available() is False


def test_a_real_backend_reads_as_available(monkeypatch: pytest.MonkeyPatch):
    import keyring

    monkeypatch.setattr(keyring, "get_keyring", lambda: object())
    assert keyring_available() is True


def test_vault_configured_follows_vault_addr(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    assert vault_configured() is False
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    assert vault_configured() is True


# -- open_store precedence --------------------------------------------------


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in ("SADDLEBAG_BACKEND", "VAULT_ADDR", "VAULT_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_keyring_is_preferred_when_available(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store_mod, "keyring_available", lambda: True)
    monkeypatch.setattr(store_mod, "vault_configured", lambda: True)
    assert open_store().name == "keyring"


def test_vault_is_the_fallback_when_no_keyring(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store_mod, "keyring_available", lambda: False)
    monkeypatch.setattr(store_mod, "VaultStore", lambda: types.SimpleNamespace(name="vault"))
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    assert open_store().name == "vault"


def test_no_store_is_a_hard_error_never_plaintext(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store_mod, "keyring_available", lambda: False)
    with pytest.raises(StoreUnavailableError) as exc:
        open_store()
    message = str(exc.value)
    # The error must tell an operator how to fix it, in both directions.
    assert "VAULT_ADDR" in message
    assert "keyring" in message


def test_explicit_keyring_backend_does_not_silently_fall_back(monkeypatch):
    monkeypatch.setattr(store_mod, "keyring_available", lambda: False)
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    with pytest.raises(StoreUnavailableError, match="no OS keyring backend"):
        open_store("keyring")


def test_backend_env_var_overrides_autodetect(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(store_mod, "keyring_available", lambda: True)
    monkeypatch.setattr(store_mod, "VaultStore", lambda: types.SimpleNamespace(name="vault"))
    monkeypatch.setenv("SADDLEBAG_BACKEND", "vault")
    assert open_store().name == "vault"


def test_unknown_backend_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SADDLEBAG_BACKEND", "s3")
    with pytest.raises(StoreUnavailableError, match="unknown SADDLEBAG_BACKEND"):
        open_store()


def test_vault_without_addr_reports_the_missing_var(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("hvac")
    with pytest.raises(StoreUnavailableError, match="VAULT_ADDR is not set"):
        open_store("vault")
