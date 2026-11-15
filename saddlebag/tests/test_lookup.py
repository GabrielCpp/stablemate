"""`secret_value`: a secret's value for Python code, over the route the session picks."""

from __future__ import annotations

import pytest

from saddlebag import SecretUnavailable, lookup, route, secret_value
from saddlebag.models import Secret
from saddlebag.route import InProcessRoute

from conftest import FakeVault

PASSWORD = "ghp_example-token-value"


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch) -> FakeVault:
    store = FakeVault()
    monkeypatch.setattr(route, "choose", lambda: InProcessRoute(store))
    return store


def test_secret_value_returns_the_stored_password_of_a_named_secret(vault: FakeVault) -> None:
    vault.create(Secret("github-token"))
    vault.set_value("github-token", "password", PASSWORD)
    assert secret_value("github-token") == PASSWORD


def test_secret_value_raises_secret_unavailable_for_an_unknown_name(vault: FakeVault) -> None:
    with pytest.raises(SecretUnavailable, match="no such secret: github-token"):
        secret_value("github-token")


def test_secret_value_names_the_missing_field_when_the_secret_holds_no_value(vault: FakeVault) -> None:
    vault.create(Secret("github-token"))
    with pytest.raises(SecretUnavailable, match="github-token has no password"):
        secret_value("github-token")


def test_secret_value_reports_a_route_that_cannot_be_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> InProcessRoute:
        raise route.RouteError("nothing listens on the socket")

    monkeypatch.setattr(route, "choose", refuse)
    with pytest.raises(SecretUnavailable, match="nothing listens on the socket"):
        lookup.secret_value("github-token")
