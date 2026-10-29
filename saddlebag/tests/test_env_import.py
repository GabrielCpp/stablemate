"""`saddlebag env import`, through the daemon and through the keyring route."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import KeyringStore
from saddlebag.store import SecretStore

from conftest import FakeBackend, Running

Run = Callable[..., int]

DOTENV = """APP_HOST=localhost
DATABASE_URL=postgres://qa:pw@localhost/db
export STRIPE_KEY='sk-live-abcdefghijklmnop'
EMPTY=
"""
URL = "postgres://qa:pw@localhost/db"
STRIPE = "sk-live-abcdefghijklmnop"


@pytest.fixture
def dotenv_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(DOTENV)
    return path


@pytest.fixture(params=["daemon", "keyring"])
def store(request: pytest.FixtureRequest) -> Callable[[], SecretStore]:
    if request.param == "daemon":
        running: Running = request.getfixturevalue("running")
        return lambda: running.vault
    request.getfixturevalue("keyring_route")
    backend: FakeBackend = request.getfixturevalue("backend")
    catalogue: Catalogue = request.getfixturevalue("catalogue")
    return lambda: KeyringStore(catalogue, backend, lambda: None)


def held(run: Run, capsys: pytest.CaptureFixture[str]) -> dict[str, dict[str, object]]:
    assert run("list", "--json") == 0
    listed = json.loads(capsys.readouterr().out)["secrets"]
    return {item["name"]: item for item in listed}


def test_import_creates_tagged_records_with_a_var_and_a_value(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,STRIPE_KEY", "--tag", "environment=local")
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == ["stored DATABASE_URL as database-url", "stored STRIPE_KEY as stripe-key"]
    records = held(run, capsys)
    assert {name: (rec["var"], rec["tags"]) for name, rec in records.items()} == {
        "database-url": ("DATABASE_URL", [["environment", "local"]]),
        "stripe-key": ("STRIPE_KEY", [["environment", "local"]]),
    }


def test_import_stores_the_value_where_the_store_can_return_it(store: Callable[[], SecretStore], run: Run, dotenv_file: Path) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,STRIPE_KEY") == 0
    holder = store()
    assert holder.value("database-url", "password") == URL
    assert holder.value("stripe-key", "password") == STRIPE


def test_prefix_leads_the_derived_name(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL", "--prefix", "local-") == 0
    assert capsys.readouterr().out.splitlines() == ["stored DATABASE_URL as local-database-url"]
    assert store().value("local-database-url", "password") == URL


def test_no_output_carries_a_value(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,STRIPE_KEY", "--json") == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data == {"file": str(dotenv_file), "stored": [{"key": "DATABASE_URL", "name": "database-url"}, {"key": "STRIPE_KEY", "name": "stripe-key"}]}
    for leaked in (URL, STRIPE, "pw@", "sk-live"):
        assert leaked not in captured.out + captured.err


def test_a_missing_key_exits_two_before_any_record_exists(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,NOPE") == 2
    assert "has no NOPE" in capsys.readouterr().err
    assert run("list", "--json") == 0
    assert json.loads(capsys.readouterr().out)["secrets"] == []


def test_an_empty_value_exits_two_before_any_record_exists(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,EMPTY") == 2
    assert "EMPTY has an empty value" in capsys.readouterr().err
    assert run("list", "--json") == 0
    assert json.loads(capsys.readouterr().out)["secrets"] == []


def test_a_duplicate_key_exits_two(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,DATABASE_URL") == 2


def test_an_existing_record_stops_the_loop_after_the_earlier_keys(store: Callable[[], SecretStore], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "create", "stripe-key") == 0
    capsys.readouterr()
    code = run("env", "import", str(dotenv_file), "--keys", "DATABASE_URL,STRIPE_KEY,APP_HOST")
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.splitlines() == ["stored DATABASE_URL as database-url"]
    assert captured.err.strip()
    assert store().value("database-url", "password") == URL
    assert run("list", "--json") == 0
    assert sorted(item["name"] for item in json.loads(capsys.readouterr().out)["secrets"]) == ["database-url", "stripe-key"]


def test_stdin_is_read_when_the_file_is_a_dash(store: Callable[[], SecretStore], run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "import", "-", "--keys", "STRIPE_KEY", stdin=DOTENV) == 0
    assert capsys.readouterr().out.splitlines() == ["stored STRIPE_KEY as stripe-key"]
    assert store().value("stripe-key", "password") == STRIPE
