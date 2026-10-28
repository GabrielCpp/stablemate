"""The record model, the SecretStore contract on the fake, and the hvac adapter's construction."""

from __future__ import annotations

import hvac
import hvac.exceptions
import pytest

from saddlebag.models import Secret, matches, parse_meta, parse_tag, validate_field, validate_meta_key, validate_name
from saddlebag.vault import VaultError, VaultStore

from conftest import FakeVault


def test_parse_tag_splits_on_the_first_equals() -> None:
    assert parse_tag("environment=local") == ("environment", "local")
    assert parse_tag("note=a=b") == ("note", "a=b")


@pytest.mark.parametrize("text", ["", "novalue", "=v", "k="])
def test_parse_tag_rejects_a_pair_missing_a_side(text: str) -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_tag(text)


def test_matches_needs_every_wanted_pair() -> None:
    tags = {("environment", "local"), ("roles", "admin")}
    assert matches(tags, [("environment", "local")])
    assert matches(tags, [("environment", "local"), ("roles", "admin")])
    assert not matches(tags, [("environment", "local"), ("roles", "reader")])
    assert matches(tags, [])


@pytest.mark.parametrize("name", ["../x", "a/b", "", "-lead", "has space"])
def test_validate_name_refuses_a_path_like_name(name: str) -> None:
    with pytest.raises(ValueError, match="invalid secret name"):
        validate_name(name)


def test_to_dict_names_which_values_exist_and_carries_none() -> None:
    secret = Secret("login", "gab", "A login", "LOGIN_PASSWORD", frozenset({("environment", "local")}), frozenset({"password"}))
    assert secret.to_dict() == {
        "name": "login",
        "username": "gab",
        "description": "A login",
        "var": "LOGIN_PASSWORD",
        "tags": [["environment", "local"]],
        "fields": ["password"],
        "metadata": {},
    }


def test_set_keeps_the_other_field(vault: FakeVault) -> None:
    vault.create(Secret("login"))
    vault.set_value("login", "password", "pw")
    vault.set_value("login", "totp", "SEED")
    assert vault.data["login"] == {"password": "pw", "totp": "SEED"}
    vault.unset_value("login", "totp")
    assert vault.data["login"] == {"password": "pw"}
    assert vault.get("login") == Secret("login", fields=frozenset({"password"}))


def test_remove_drops_metadata_and_data(vault: FakeVault) -> None:
    vault.create(Secret("login"))
    vault.set_value("login", "password", "pw")
    vault.remove("login")
    assert vault.get("login") is None
    assert vault.names() == []
    assert "login" not in vault.data


def test_the_vault_store_connects_with_the_token_it_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, url: str, token: str) -> None:
            seen.update(url=url, token=token)

        def is_authenticated(self) -> bool:
            return True

    monkeypatch.setattr(hvac, "Client", FakeClient)
    store = VaultStore("http://127.0.0.1:8200", "root")
    assert seen == {"url": "http://127.0.0.1:8200", "token": "root"}
    assert store.is_authenticated()


def test_the_vault_store_refuses_a_rejected_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *, url: str, token: str) -> None:
            pass

        def is_authenticated(self) -> bool:
            return False

    monkeypatch.setattr(hvac, "Client", FakeClient)
    with pytest.raises(VaultError, match="rejected the token"):
        VaultStore("http://127.0.0.1:8200", "bad")


def test_parse_meta_splits_on_the_first_equals() -> None:
    assert parse_meta("phone=+15555550100") == ("phone", "+15555550100")
    assert parse_meta(" note = a=b ") == ("note", "a=b")


@pytest.mark.parametrize("text", ["", "novalue", "=v", "k="])
def test_parse_meta_rejects_a_pair_missing_a_side(text: str) -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_meta(text)


@pytest.mark.parametrize("key", ["a.b", "-lead", "has space", "", "a=b"])
def test_a_metadata_key_has_no_dot_or_equals(key: str) -> None:
    with pytest.raises(ValueError, match="invalid metadata key"):
        validate_meta_key(key)


def test_validate_field_accepts_meta_only_with_the_full_field_list() -> None:
    assert validate_field("meta.phone") == "meta.phone"
    with pytest.raises(ValueError, match=r"meta\.<key>"):
        validate_field("nope")
    with pytest.raises(ValueError, match="unknown field"):
        validate_field("meta.phone", ("password", "totp"))
    with pytest.raises(ValueError, match="invalid metadata key"):
        validate_field("meta.a.b")


def test_to_dict_carries_sorted_metadata() -> None:
    assert Secret("login", metadata={"b": "2", "a": "1"}).to_dict()["metadata"] == {"a": "1", "b": "2"}


class FakeKv:
    def __init__(self) -> None:
        self.custom: dict[str, str] = {}
        self.data: dict[str, str] = {}
        self.absent = False

    def update_metadata(self, *, path: str, mount_point: str, custom_metadata: dict[str, str]) -> None:
        self.custom = custom_metadata

    def read_secret_metadata(self, *, path: str, mount_point: str) -> dict[str, object]:
        if self.absent:
            raise hvac.exceptions.InvalidPath()
        return {"data": {"custom_metadata": self.custom}}

    def read_secret_version(self, *, path: str, mount_point: str, raise_on_deleted_version: bool) -> dict[str, object]:
        return {"data": {"data": self.data}}


@pytest.fixture
def kv_store(monkeypatch: pytest.MonkeyPatch) -> tuple[VaultStore, FakeKv]:
    kv = FakeKv()

    class FakeClient:
        def __init__(self, *, url: str, token: str) -> None:
            self.secrets = type("Secrets", (), {"kv": type("Kv", (), {"v2": kv})()})()

        def is_authenticated(self) -> bool:
            return True

    monkeypatch.setattr(hvac, "Client", FakeClient)
    return VaultStore("http://127.0.0.1:8200", "root"), kv


def test_the_vault_store_writes_and_reads_metadata_as_json(kv_store: tuple[VaultStore, FakeKv]) -> None:
    store, kv = kv_store
    store.create(Secret("login", "gab", metadata={"role": "admin", "phone": "+1"}))
    assert kv.custom["metadata"] == '{"phone": "+1", "role": "admin"}'
    secret = store.get("login")
    assert secret is not None and secret.metadata == {"phone": "+1", "role": "admin"}
    assert store.value("login", "meta.phone") == "+1"
    assert store.value("login", "meta.absent") is None


def test_a_record_written_before_metadata_reads_empty(kv_store: tuple[VaultStore, FakeKv]) -> None:
    store, kv = kv_store
    kv.custom = {"username": "gab", "tags": "[]"}
    secret = store.get("login")
    assert secret is not None and secret.metadata == {}


def test_retag_keeps_metadata_and_set_metadata_keeps_tags(kv_store: tuple[VaultStore, FakeKv]) -> None:
    store, _ = kv_store
    store.create(Secret("login", "gab", "d", "V", frozenset({("a", "b")}), metadata={"k": "v"}))
    store.retag("login", frozenset({("c", "d")}))
    secret = store.get("login")
    assert secret is not None and secret.metadata == {"k": "v"} and secret.tags == {("c", "d")} and secret.var == "V"
    store.set_metadata("login", {"z": "1"})
    secret = store.get("login")
    assert secret is not None and secret.metadata == {"z": "1"} and secret.tags == {("c", "d")}


def test_set_metadata_on_a_missing_secret_is_an_error(kv_store: tuple[VaultStore, FakeKv]) -> None:
    store, kv = kv_store
    kv.absent = True
    with pytest.raises(VaultError, match="no such secret"):
        store.set_metadata("ghost", {"k": "v"})
