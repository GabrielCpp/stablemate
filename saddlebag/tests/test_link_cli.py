"""``link``, ``unlink`` and ``add --password-keychain``: reading a secret in place.

The invariant under test is that a credential's secret has exactly one home. saddlebag
either holds it or points at it, never both — because the copy is the one that goes
stale silently, and a login presenting a rotated-away password against an account that
locks is the most expensive way to find that out.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from saddlebag import cli, keychain
from saddlebag.db import Pool
from saddlebag.models import KeychainRef

PASSWORD = "s3cret-from-the-keychain"
SEED = "GEZDGNBVGY3TQOJQ"


class FakeItem:
    def __init__(self, label: str, secret: str, attributes: dict[str, str]):
        self.label = label
        self.secret = secret
        self.attributes = attributes

    def get_label(self) -> str:
        return self.label

    def get_attributes(self) -> dict[str, str]:
        return self.attributes

    def is_locked(self) -> bool:
        return False

    def get_secret(self) -> bytes:
        return self.secret.encode("utf-8")


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, store):
    monkeypatch.setattr(cli, "open_store", lambda backend=None: store)
    return store


@pytest.fixture(autouse=True)
def no_inferred_project(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "infer_project", lambda: None)


@pytest.fixture
def keychain_items(monkeypatch: pytest.MonkeyPatch):
    """A fake Secret Service holding one password and one seed for the same account."""
    catalogue = [
        FakeItem("bot password", PASSWORD,
                 {"service": "github", "account": "bot", "type": "password"}),
        FakeItem("bot TOTP", SEED,
                 {"service": "github", "account": "bot", "type": "totp"}),
    ]

    def search(attributes: dict[str, str]) -> list[FakeItem]:
        return [i for i in catalogue if attributes.items() <= i.attributes.items()]

    monkeypatch.setattr(keychain, "_search", search)
    return catalogue


@pytest.fixture
def run(db_path: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    def _run(*argv: str, stdin: str | None = None) -> int:
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            cli.main(["--db", str(db_path), *argv])
        code = exc.value.code
        assert isinstance(code, int)
        return code

    return _run


@pytest.fixture
def stored(run):
    """A credential whose password saddlebag holds itself."""
    assert run("add", "--username", "bot", "--env", "prod", "--password-stdin",
               stdin="hunter2") == 0
    return "cred-001"


def credential(db_path: Path, credential_id: str = "cred-001"):
    with Pool(db_path) as pool:
        cred = pool.get(credential_id)
    assert cred is not None
    return cred


# -- add --password-keychain -------------------------------------------------


def test_add_records_the_address_and_stores_nothing(run, db_path, store, keychain_items, capsys):
    assert run("add", "--username", "bot", "--env", "prod", "--password-keychain",
               "service=github", "account=bot", "type=password") == 0

    cred = credential(db_path)
    assert cred.password_ref is not None
    assert cred.password_ref.describe() == "account=bot service=github type=password"
    # The whole point: no second copy anywhere in saddlebag's own store.
    assert store.get(cred.store_key) is None
    assert PASSWORD not in capsys.readouterr().out


def test_add_refuses_an_address_that_does_not_resolve(run, db_path, keychain_items):
    # Recorded-but-broken is the state worth refusing: the pool would read as healthy
    # right up to the moment a run needed the password.
    assert run("add", "--username", "bot", "--env", "prod", "--password-keychain",
               "service=gitlab") == 1
    with Pool(db_path) as pool:
        assert pool.all() == []


def test_add_refuses_an_ambiguous_address(run, db_path, keychain_items):
    assert run("add", "--username", "bot", "--env", "prod", "--password-keychain",
               "service=github", "account=bot") == 1
    with Pool(db_path) as pool:
        assert pool.all() == []


def test_a_linked_credential_can_be_leased(run, stored, db_path, keychain_items, capsys):
    # `acquire` checks a password is readable before handing out a lease. That check
    # has to follow the reference, or linking would make every credential unleaseable.
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    assert run("acquire", "cred-001") == 0
    assert PASSWORD not in capsys.readouterr().out


# -- link --------------------------------------------------------------------


def test_link_refuses_to_shadow_a_stored_password(run, stored, db_path, keychain_items):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password") == 1
    assert credential(db_path).password_ref is None


def test_force_drops_the_stored_copy_it_would_have_shadowed(run, stored, store, db_path,
                                                             keychain_items):
    cred = credential(db_path)
    assert store.get(cred.store_key) == "hunter2"

    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    assert store.get(cred.store_key) is None
    assert credential(db_path).password_ref is not None


def test_link_reports_the_address_and_not_the_secret(run, stored, keychain_items, capsys, caplog):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    captured = capsys.readouterr()
    assert "service=github" in captured.out
    assert PASSWORD not in captured.out
    assert PASSWORD not in captured.err
    assert PASSWORD not in caplog.text


def test_link_on_an_unknown_credential_says_so(run, keychain_items):
    assert run("link", "cred-404", "service=github", "type=password") == 1


def test_link_refuses_an_address_matching_nothing(run, stored, db_path, keychain_items):
    assert run("link", "cred-001", "service=gitlab", "--force") == 1
    assert credential(db_path).password_ref is None


def test_the_seed_links_separately_from_the_password(run, stored, db_path, keychain_items):
    assert run("link", "cred-001", "service=github", "account=bot", "type=totp",
               "--field", "totp") == 0
    cred = credential(db_path)
    assert cred.totp_ref is not None
    assert cred.password_ref is None


# -- what a linked credential does next --------------------------------------


def test_totp_set_refuses_to_write_a_seed_that_would_be_ignored(run, stored, keychain_items):
    assert run("link", "cred-001", "service=github", "account=bot", "type=totp",
               "--field", "totp") == 0
    # Writing here would be inert — `seed_for` reads the reference first — and an
    # operator would have no way to tell from the outside.
    assert run("totp", "set", "cred-001", stdin=SEED) == 1


def test_unlink_leaves_the_keychain_item_alone(run, stored, db_path, keychain_items, capsys):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    assert run("unlink", "cred-001") == 0

    assert credential(db_path).password_ref is None
    assert "untouched" in capsys.readouterr().out
    # saddlebag did not write that item, so it does not delete it.
    still_there = KeychainRef.of({"service": "github", "account": "bot", "type": "password"})
    assert keychain.lookup(still_there) == PASSWORD


def test_unlink_on_an_unlinked_credential_says_so(run, stored):
    assert run("unlink", "cred-001") == 1


def test_remove_says_which_keychain_item_it_left_behind(run, stored, keychain_items, capsys):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    assert run("remove", "cred-001") == 0
    out = capsys.readouterr().out
    assert "untouched" in out
    assert "service=github" in out


def test_doctor_reports_a_reference_that_stopped_resolving(run, stored, db_path,
                                                            keychain_items, monkeypatch, capsys):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    # The item is renamed, deleted, or its attributes change at the source — the pool
    # still reads as fine until something asks for the password. `doctor` is where that
    # is supposed to surface.
    monkeypatch.setattr(keychain, "_search", lambda _: [])
    assert run("doctor", "--json") == 1
    assert json.loads(capsys.readouterr().out)["orphans"] == ["cred-001"]


def test_list_shows_where_a_secret_comes_from_without_showing_it(run, stored, keychain_items,
                                                                  capsys):
    assert run("link", "cred-001", "service=github", "account=bot", "type=password",
               "--force") == 0
    assert run("list", "--json") == 0
    payload = capsys.readouterr().out
    assert PASSWORD not in payload
    assert json.loads(payload)[0]["password_ref"] == "account=bot service=github type=password"
