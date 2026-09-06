"""Reading a secret out of a keychain item saddlebag did not write.

The Secret Service itself is stubbed at :func:`saddlebag.keychain._search` — the one
function that talks to D-Bus. Everything above it is the part with decisions in it:
which item a query names, what happens when it names two, and which of a credential's
two possible homes a read goes to.
"""

from __future__ import annotations

import pytest

from saddlebag import keychain
from saddlebag.models import Credential, KeychainRef


class FakeItem:
    def __init__(self, label: str, secret: str, attributes: dict[str, str], locked: bool = False):
        self._label = label
        self._secret = secret
        self._attributes = attributes
        self._locked = locked

    def get_label(self) -> str:
        return self._label

    def get_attributes(self) -> dict[str, str]:
        return self._attributes

    def is_locked(self) -> bool:
        return self._locked

    def get_secret(self) -> bytes:
        return self._secret.encode("utf-8")


class FakeStore:
    """The saddlebag-owned store, so a test can tell the two homes apart."""

    name = "keyring"

    def __init__(self, values: dict[str, str] | None = None):
        self.values = values or {}

    # Parameter names mirror the SecretStore protocol exactly — a fake whose signature
    # has drifted from the port stops standing in for it.
    def put(self, credential_id: str, password: str) -> None:
        self.values[credential_id] = password

    def get(self, credential_id: str) -> str | None:
        return self.values.get(credential_id)

    def delete(self, credential_id: str) -> None:
        self.values.pop(credential_id, None)


PASSWORD_ITEM = FakeItem(
    "bot password",
    "s3cret-from-the-keychain",
    {"service": "github", "account": "bot", "type": "password", "xdg:schema": "org.freedesktop.Secret.Generic"},
)
SEED_ITEM = FakeItem(
    "bot TOTP",
    "VNHP5MU6JYZSS4G3",
    {"service": "github", "account": "bot", "type": "totp"},
)


@pytest.fixture
def items(monkeypatch):
    """Every item on the fake keychain; a search matches attribute supersets, as the real one does."""
    catalogue: list[FakeItem] = [PASSWORD_ITEM, SEED_ITEM]

    def search(attributes: dict[str, str]) -> list[FakeItem]:
        return [i for i in catalogue if attributes.items() <= i.get_attributes().items()]

    monkeypatch.setattr(keychain, "_search", search)
    return catalogue


def ref(**attributes: str) -> KeychainRef:
    return KeychainRef.of(attributes)


def test_an_exact_query_reads_the_item(items):
    assert keychain.lookup(ref(service="github", account="bot", type="password")) == (
        "s3cret-from-the-keychain"
    )


def test_a_query_matching_two_items_is_an_error_naming_both(items):
    # The failure this exists to prevent: `service=github account=bot` also matches the
    # TOTP seed, and answering it with whichever sorted first would type a seed into a
    # password field — a login that fails for a reason nothing in the trace explains.
    with pytest.raises(keychain.KeychainError) as exc:
        keychain.lookup(ref(service="github", account="bot"))
    assert "2 keychain items" in str(exc.value)
    assert "bot password" in str(exc.value)
    assert "bot TOTP" in str(exc.value)


def test_the_error_for_two_matches_carries_no_secret(items):
    with pytest.raises(keychain.KeychainError) as exc:
        keychain.lookup(ref(service="github", account="bot"))
    assert "s3cret-from-the-keychain" not in str(exc.value)
    assert "VNHP5MU6JYZSS4G3" not in str(exc.value)


def test_no_match_says_what_was_searched_for(items):
    with pytest.raises(keychain.KeychainError, match="no keychain item matches"):
        keychain.lookup(ref(service="gitlab", account="bot"))


def test_a_locked_item_is_diagnosed_rather_than_read(monkeypatch):
    locked = FakeItem("bot password", "unreachable", {"service": "github"}, locked=True)
    monkeypatch.setattr(keychain, "_search", lambda _: [locked])
    with pytest.raises(keychain.KeychainError, match="is locked"):
        keychain.lookup(ref(service="github"))


def test_attributes_parse_on_the_first_equals_only():
    assert keychain.parse_attributes(["service=github", "note=a=b"]) == {
        "service": "github",
        "note": "a=b",
    }


@pytest.mark.parametrize("pair", ["service", "=github", ""])
def test_an_attribute_that_is_not_name_equals_value_is_refused(pair):
    # A pair that silently became `{"": ""}` would widen the query rather than narrow
    # it, and a widened query is how the wrong item gets read.
    with pytest.raises(keychain.KeychainError, match="name=value"):
        keychain.parse_attributes([pair])


def test_an_empty_reference_is_refused():
    with pytest.raises(keychain.KeychainError, match="at least one attribute"):
        keychain.parse_attributes([])


def test_item_attributes_drops_the_ones_the_service_owns(items):
    assert keychain.item_attributes(["service=github", "type=password"]) == {
        "service": "github",
        "account": "bot",
        "type": "password",
    }


def test_a_credential_with_no_reference_reads_the_saddlebag_store(items):
    cred = Credential(id="cred-001", username="bot", env="prod")
    store = FakeStore({cred.store_key: "stored-here"})
    assert keychain.password_for(cred, store) == "stored-here"


def test_a_reference_wins_over_a_stored_copy(items):
    # There should never be both — `link` refuses to create that state — but if one
    # appears anyway, the reference is what the credential says is authoritative, and
    # silently preferring the stale copy is the failure mode this whole module exists
    # to avoid.
    cred = Credential(
        id="cred-001",
        username="bot",
        env="prod",
        password_ref=ref(service="github", account="bot", type="password"),
    )
    store = FakeStore({cred.store_key: "stale-copy"})
    assert keychain.password_for(cred, store) == "s3cret-from-the-keychain"


def test_the_seed_resolves_through_its_own_reference(items):
    cred = Credential(
        id="cred-001",
        username="bot",
        env="prod",
        totp_ref=ref(service="github", account="bot", type="totp"),
    )
    assert keychain.seed_for(cred, FakeStore()) == "VNHP5MU6JYZSS4G3"


def test_the_two_references_are_independent(items):
    cred = Credential(
        id="cred-001",
        username="bot",
        env="prod",
        password_ref=ref(service="github", account="bot", type="password"),
    )
    store = FakeStore({cred.totp_store_key: "SEEDFROMTHESTORE"})
    assert keychain.password_for(cred, store) == "s3cret-from-the-keychain"
    assert keychain.seed_for(cred, store) == "SEEDFROMTHESTORE"


def test_a_reference_describes_itself_in_a_stable_order():
    assert ref(type="password", service="github").describe() == "service=github type=password"
