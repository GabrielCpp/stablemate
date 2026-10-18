"""The record model, the SecretStore contract on the fake, and the hvac adapter's construction."""

from __future__ import annotations

import pytest

from saddlebag import vault as vault_mod
from saddlebag.models import Secret, matches, parse_tag, validate_name
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

    monkeypatch.setattr(vault_mod.hvac, "Client", FakeClient)
    store = VaultStore("http://127.0.0.1:8200", "root")
    assert seen == {"url": "http://127.0.0.1:8200", "token": "root"}
    assert store.is_authenticated()


def test_the_vault_store_refuses_a_rejected_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *, url: str, token: str) -> None:
            pass

        def is_authenticated(self) -> bool:
            return False

    monkeypatch.setattr(vault_mod.hvac, "Client", FakeClient)
    with pytest.raises(VaultError, match="rejected the token"):
        VaultStore("http://127.0.0.1:8200", "bad")
