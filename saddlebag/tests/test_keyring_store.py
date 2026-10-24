"""The keyring shelf and its door."""

from __future__ import annotations

import keyring
import keyring.backend
import keyring.backends.fail
import keyring.backends.null
import keyring.errors
import pytest

from saddlebag import keyring_store
from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import SERVICE, KeyringStore, open_door
from saddlebag.models import Secret
from saddlebag.store import StoreUnavailable

from conftest import FakeBackend


@pytest.fixture
def store(catalogue: Catalogue, backend: FakeBackend) -> KeyringStore:
    shelf = KeyringStore(catalogue, backend)
    shelf.create(Secret("login", "gab", tags=frozenset({("environment", "local")})))
    return shelf


def test_set_records_the_field_and_keeps_the_value_in_the_keyring(store: KeyringStore, backend: FakeBackend) -> None:
    store.set_value("login", "password", "pw")
    store.set_value("login", "totp", "SEED")
    secret = store.get("login")
    assert secret is not None and secret.fields == frozenset({"password", "totp"})
    assert backend.items[(SERVICE, "login/password")] == "pw"
    assert store.value("login", "password") == "pw"
    assert store.value("login", "totp") == "SEED"
    assert store.value("login", "missing") is None


def test_username_comes_from_the_record(store: KeyringStore, backend: FakeBackend) -> None:
    assert store.value("login", "username") == "gab"
    assert backend.items == {}


def test_create_stores_no_fields(store: KeyringStore) -> None:
    store.create(Secret("other", fields=frozenset({"password"})))
    other = store.get("other")
    assert other is not None and other.fields == frozenset()


def test_unset_clears_both_places(store: KeyringStore, backend: FakeBackend) -> None:
    store.set_value("login", "password", "pw")
    store.unset_value("login", "password")
    store.unset_value("login", "password")
    secret = store.get("login")
    assert secret is not None and secret.fields == frozenset()
    assert backend.items == {}


def test_remove_clears_both_places(store: KeyringStore, backend: FakeBackend) -> None:
    store.set_value("login", "password", "pw")
    store.remove("login")
    assert store.get("login") is None
    assert store.names() == []
    assert backend.items == {}


def test_retag_replaces_the_tags(store: KeyringStore) -> None:
    store.retag("login", frozenset({("roles", "admin")}))
    secret = store.get("login")
    assert secret is not None and secret.tags == frozenset({("roles", "admin")})


def test_set_on_a_missing_record_is_refused(store: KeyringStore, backend: FakeBackend) -> None:
    with pytest.raises(StoreUnavailable, match="no such secret: ghost"):
        store.set_value("ghost", "password", "pw")
    assert backend.items == {}


@pytest.mark.parametrize("backend_class", [keyring.backends.fail.Keyring, keyring.backends.null.Keyring])
def test_a_backend_outside_the_allow_list_is_absent(monkeypatch: pytest.MonkeyPatch, backend_class: type[keyring.backend.KeyringBackend]) -> None:
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend_class())
    with pytest.raises(StoreUnavailable, match="no OS keyring on this session"):
        open_door()


class Failing(FakeBackend):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def get_password(self, service: str, username: str) -> str | None:
        raise self.error


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (keyring.errors.KeyringLocked("locked"), "the OS keyring is locked"),
        (keyring.errors.NoKeyringError("none"), "no OS keyring on this session"),
        (keyring.errors.InitError("init"), "no OS keyring on this session"),
        (keyring.errors.KeyringError("refused"), "the Keychain refused this interpreter"),
    ],
)
def test_a_backend_error_says_what_the_operator_does_next(catalogue: Catalogue, error: Exception, text: str) -> None:
    store = KeyringStore(catalogue, Failing(error))
    with pytest.raises(StoreUnavailable, match=text):
        store.value("login", "password")


def test_the_distrust_message_names_the_account(catalogue: Catalogue) -> None:
    store = KeyringStore(catalogue, Failing(keyring.errors.KeyringError("refused")))
    with pytest.raises(StoreUnavailable, match=f"-s {keyring_store.SERVICE} -a login/password"):
        store.value("login", "password")


def test_health_without_an_enumerator_cannot_name_orphans(store: KeyringStore) -> None:
    store.set_value("login", "password", "pw")
    health = store.health()
    assert health.backend == "keyring"
    assert health.reachable
    assert health.missing_items == ()
    assert health.orphan_items is None


def test_health_names_drift_and_orphans(catalogue: Catalogue, backend: FakeBackend) -> None:
    shelf = KeyringStore(catalogue, backend, lambda: sorted(a for s, a in backend.items if s == SERVICE))
    shelf.create(Secret("login"))
    shelf.set_value("login", "password", "pw")
    backend.items[(SERVICE, "ghost/password")] = "x"
    del backend.items[(SERVICE, "login/password")]
    health = shelf.health()
    assert health.missing_items == ("login/password",)
    assert health.orphan_items == ("ghost/password",)
