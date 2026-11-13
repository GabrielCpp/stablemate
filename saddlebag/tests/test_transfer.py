"""Export and import: a whole store as one plaintext JSON file, and back, on both routes."""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import transfer
from saddlebag.catalogue import Catalogue
from saddlebag.keyring_store import SERVICE
from saddlebag.models import Secret
from saddlebag.store import StoreUnavailable

from conftest import FakeBackend, FakeVault, Running

Run = Callable[..., int]

PASSWORD = "correct-horse-9f3k2m"
SEED = "JBSWY3DPEHPK3PXP"


@pytest.fixture
def at_terminal(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    monkeypatch.setattr("saddlebag.cli._operator_present", lambda: True)

    def answer(yes: bool) -> None:
        monkeypatch.setattr("saddlebag.cli._confirmed", lambda question: yes)

    answer(True)
    return answer


def seed_store(run: Run) -> None:
    assert run("secret", "create", "admin", "--username", "root", "--var", "ADMIN_PASSWORD", "--tag", "environment=local", "--meta", "phone=+15555550100") == 0
    assert run("secret", "set", "admin", stdin=PASSWORD) == 0
    assert run("secret", "set", "admin", "--field", "totp", stdin=SEED) == 0
    assert run("secret", "create", "bare", "--description", "no value yet") == 0
    assert run("secret", "create", "deploy-token", "--tag", "environment=staging", "--tag", "role=ci") == 0
    assert run("secret", "set", "deploy-token", stdin="tok-0123456789abcdef") == 0


def fresh_keyring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str) -> FakeBackend:
    backend = FakeBackend()
    catalogue = Catalogue(tmp_path / label / "catalogue.json")
    monkeypatch.setattr(Catalogue, "default", classmethod(lambda cls: catalogue))
    monkeypatch.setattr("saddlebag.route.open_door", lambda: backend)
    return backend


def test_a_keyring_store_round_trips_byte_for_byte(
    keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_store(run)
    first = tmp_path / "first.saddlebag.json"
    assert run("export", str(first)) == 0
    target = fresh_keyring(monkeypatch, tmp_path, "target")
    assert run("import", str(first)) == 0
    at_terminal(True)
    second = tmp_path / "second.saddlebag.json"
    assert run("export", str(second)) == 0
    assert second.read_bytes() == first.read_bytes()
    assert target.items[(SERVICE, "admin/totp")] == SEED


def test_the_export_holds_every_attribute_and_value(keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path) -> None:
    seed_store(run)
    path = tmp_path / "backup.saddlebag.json"
    assert run("export", str(path)) == 0
    document = json.loads(path.read_text())
    assert document["format"] == "saddlebag-export" and document["version"] == 1
    assert [entry["name"] for entry in document["secrets"]] == ["admin", "bare", "deploy-token"]
    assert document["secrets"][0] == {
        "name": "admin",
        "username": "root",
        "description": None,
        "var": "ADMIN_PASSWORD",
        "tags": [["environment", "local"]],
        "metadata": {"phone": "+15555550100"},
        "values": {"password": PASSWORD, "totp": SEED},
    }
    assert document["secrets"][1]["values"] == {"password": "", "totp": ""}


def test_the_export_file_is_owner_only(keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path) -> None:
    seed_store(run)
    path = tmp_path / "backup.saddlebag.json"
    assert run("export", str(path)) == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_export_off_a_terminal_is_refused_before_any_request(
    keyring_route: FakeBackend, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_store(run)

    def no_route() -> None:
        raise AssertionError("export reached the store")

    monkeypatch.setattr("saddlebag.route.choose", no_route)
    path = tmp_path / "backup.saddlebag.json"
    assert run("export", str(path), stdin="y\n") == 2
    assert "terminal" in capsys.readouterr().err
    assert not path.exists()


def test_export_refuses_a_name_the_guard_does_not_know(keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path) -> None:
    path = tmp_path / "backup.json"
    assert run("export", str(path)) == 2
    assert not path.exists()


def test_export_never_replaces_a_file(keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path) -> None:
    seed_store(run)
    path = tmp_path / "backup.saddlebag.json"
    path.write_text("keep me")
    assert run("export", str(path)) == 1
    assert path.read_text() == "keep me"


def test_export_stops_unless_the_operator_says_yes(keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path) -> None:
    seed_store(run)
    at_terminal(False)
    path = tmp_path / "backup.saddlebag.json"
    assert run("export", str(path)) == 1
    assert not path.exists()


def test_a_value_missing_from_the_keyring_exports_empty(
    keyring_route: FakeBackend, run: Run, at_terminal: Callable[[bool], None], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_store(run)
    del keyring_route.items[(SERVICE, "deploy-token/password")]
    path = tmp_path / "backup.saddlebag.json"
    assert run("export", str(path)) == 0
    entry = json.loads(path.read_text())["secrets"][2]
    assert entry["values"] == {"password": "", "totp": ""}
    assert capsys.readouterr().err == ""


def test_an_empty_value_imports_as_no_value(keyring_route: FakeBackend, run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"format": "saddlebag-export", "version": 1, "secrets": [{"name": "bare", "values": {"password": "", "totp": ""}}]}
    path = tmp_path / "in.saddlebag.json"
    path.write_text(json.dumps(payload))
    assert run("import", str(path)) == 0
    assert run("list", "--json") == 0
    listed = json.loads(capsys.readouterr().out)["secrets"]
    assert listed[0]["name"] == "bare" and listed[0]["fields"] == []
    assert keyring_route.items == {}


def test_import_refuses_every_problem_before_the_first_write(
    keyring_route: FakeBackend, run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_store(run)
    before = dict(keyring_route.items)
    payload = {
        "format": "saddlebag-export",
        "version": 1,
        "secrets": [
            {"name": "newcomer", "values": {"password": "fresh-value-123"}},
            {"name": "admin", "values": {"password": "other"}},
            {"name": "otp", "values": {"totp": "not!base32"}},
        ],
    }
    path = tmp_path / "in.saddlebag.json"
    path.write_text(json.dumps(payload))
    assert run("import", str(path)) == 1
    err = capsys.readouterr().err
    assert "already in the store: admin" in err and "'otp'" in err and "not!base32" not in err
    assert keyring_route.items == before
    assert run("list", "--json") == 0
    assert "newcomer" not in capsys.readouterr().out


def test_replace_makes_the_file_win_whole(keyring_route: FakeBackend, run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seed_store(run)
    payload = {
        "format": "saddlebag-export",
        "version": 1,
        "secrets": [{"name": "admin", "username": "ops", "tags": [["environment", "prod"]], "values": {"password": "rotated-value-42", "totp": ""}}],
    }
    path = tmp_path / "in.saddlebag.json"
    path.write_text(json.dumps(payload))
    assert run("import", str(path), "--replace") == 0
    assert keyring_route.items[(SERVICE, "admin/password")] == "rotated-value-42"
    assert (SERVICE, "admin/totp") not in keyring_route.items
    assert run("list", "--json") == 0
    admin = next(entry for entry in json.loads(capsys.readouterr().out)["secrets"] if entry["name"] == "admin")
    assert admin["username"] == "ops" and admin["tags"] == [["environment", "prod"]] and admin["metadata"] == {}


@pytest.mark.parametrize(
    ("payload", "says"),
    [
        ({"secrets": []}, "not a saddlebag export"),
        ({"format": "saddlebag-export", "version": 2, "secrets": []}, "unsupported export version 2"),
        ({"format": "saddlebag-export", "version": 1, "secrets": [{"name": "a", "colour": "red"}]}, "unknown keys colour"),
        ({"format": "saddlebag-export", "version": 1, "secrets": [{"name": "a"}, {"name": "a"}]}, "appears twice"),
        ({"format": "saddlebag-export", "version": 1, "secrets": [{"name": "a", "values": {"pin": "1"}}]}, "unknown value 'pin'"),
        ({"format": "saddlebag-export", "version": 1, "secrets": [{"name": "bad name"}]}, "invalid secret name"),
    ],
)
def test_the_reader_refuses_what_it_cannot_load(payload: object, says: str) -> None:
    with pytest.raises(transfer.DocumentError, match=says):
        transfer.read(payload)


def test_import_names_unreadable_json_without_quoting_it(keyring_route: FakeBackend, run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "in.saddlebag.json"
    path.write_text('{"secrets": [{"values": {"password": "' + PASSWORD + '"}')
    assert run("import", str(path)) == 2
    assert PASSWORD not in capsys.readouterr().err


class FailingStore(FakeVault):
    def set_value(self, name: str, field: str, value: str) -> None:
        if name == "second":
            raise StoreUnavailable("the OS keyring is locked")
        super().set_value(name, field, value)


def test_a_store_failure_names_what_was_imported_before_it() -> None:
    payload = transfer.document([transfer.ExportedSecret(Secret(name), {"password": "value-of-" + name}) for name in ("first", "second", "third")])
    with pytest.raises(transfer.ImportInterrupted, match=r"failed on second \(the OS keyring is locked\); imported before it: first"):
        transfer.load(FailingStore(), payload)


def test_the_daemon_round_trips_and_logs_no_value(running: Running, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    running.ask("create", name="login", username="gab", var="LOGIN_PASSWORD", tags=["environment=local"])
    running.ask("set", name="login", field="password", value=PASSWORD)
    exported = running.ask("export")
    assert exported.ok
    first = transfer.render(exported.result["document"])
    running.vault.metadata.clear()
    running.vault.data.clear()
    assert running.ask("import", document=json.loads(first), replace=False).result == {"imported": ["login"]}
    assert transfer.render(running.ask("export").result["document"]) == first
    assert PASSWORD not in caplog.text
