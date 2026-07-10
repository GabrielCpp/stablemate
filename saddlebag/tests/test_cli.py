"""End-to-end CLI behaviour: exit codes, redaction, and the lease bookend."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from saddlebag import cli
from saddlebag.db import Pool


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, store):
    """Every CLI invocation gets the same in-memory fake store — never the real keyring."""
    monkeypatch.setattr(cli, "open_store", lambda backend=None: store)
    return store


@pytest.fixture
def run(db_path: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    """Invoke ``main()`` against the temp pool and return its exit code.

    Captured output is discarded before each invocation, so ``out(capsys)`` after a
    call yields that command's output alone and not the residue of a setup step.
    """
    def _run(*argv: str, stdin: str | None = None) -> int:
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            cli.main(["--db", str(db_path), *argv])
        return exc.value.code

    return _run


@pytest.fixture
def add_one(run):
    def _add(username: str = "admin@staging.example.com", env: str = "staging",
             roles: tuple[str, ...] = ("admin", "billing"), password: str = "hunter2") -> int:
        return run("add", "--username", username, "--env", env,
                   "--roles", *roles, "--password-stdin", stdin=password)

    return _add


def out(capsys) -> str:
    return capsys.readouterr().out


# -- add --------------------------------------------------------------------


def test_add_stores_metadata_in_pool_and_password_in_store(add_one, db_path, store):
    assert add_one() == 0
    with Pool(db_path) as pool:
        cred = pool.get("cred-001")
    assert cred.username == "admin@staging.example.com"
    assert cred.roles == ("admin", "billing")
    assert store.get("cred-001") == "hunter2"


def test_add_without_password_stdin_is_a_usage_error(run):
    assert run("add", "--username", "a@x.com", "--env", "staging") == 2


def test_add_with_empty_stdin_is_a_usage_error(run):
    assert run("add", "--username", "a@x.com", "--env", "staging",
               "--password-stdin", stdin="   \n") == 2


def test_add_rolls_back_metadata_when_the_store_write_fails(db_path, monkeypatch, store):
    """A credential whose password never landed must not linger in the pool."""
    def explode(credential_id: str, password: str) -> None:
        raise RuntimeError("keyring is locked")

    monkeypatch.setattr(store, "put", explode)
    monkeypatch.setattr("sys.stdin", io.StringIO("hunter2"))
    with pytest.raises(RuntimeError, match="keyring is locked"):
        cli.main(["--db", str(db_path), "add", "--username", "a@x.com",
                  "--env", "staging", "--password-stdin"])

    with Pool(db_path) as pool:
        assert pool.all() == []


# -- list -------------------------------------------------------------------


def test_list_json_never_emits_a_password(add_one, run, capsys):
    add_one()
    assert run("list", "--json") == 0
    payload = out(capsys)
    assert "hunter2" not in payload
    assert "password" not in payload
    assert json.loads(payload)[0]["id"] == "cred-001"


def test_list_filters_by_env(add_one, run, capsys):
    add_one(username="a@staging.com", env="staging")
    add_one(username="b@prod.com", env="prod")

    run("list", "--env", "prod", "--json")
    rows = json.loads(out(capsys))
    assert [r["username"] for r in rows] == ["b@prod.com"]


def test_list_shows_locked_credentials(add_one, run, capsys):
    add_one()
    run("acquire", "cred-001")
    run("list", "--json")
    assert json.loads(out(capsys))[0]["locked"] is True


# -- scan -------------------------------------------------------------------


def test_scan_json_lists_candidates_without_leasing(add_one, run, capsys, db_path):
    add_one()
    assert run("scan", "--env", "staging", "--roles", "admin", "--json") == 0
    assert json.loads(out(capsys))[0]["id"] == "cred-001"

    with Pool(db_path) as pool:
        assert not pool.get("cred-001").is_locked()


def test_scan_excludes_leased_credentials(add_one, run, capsys):
    add_one()
    run("acquire", "cred-001")
    run("scan", "--env", "staging", "--json")
    assert json.loads(out(capsys)) == []


def test_scan_with_select_via_leases_the_agents_choice(add_one, run, monkeypatch, tmp_path, db_path):
    add_one()
    monkeypatch.setattr(cli, "select", lambda req, cands, agent: (cands[0], _sel()))

    output = tmp_path / ".workhorse" / "credential.json"
    code = run("scan", "--env", "staging", "--roles", "admin",
               "--select-via", "claude", "--run-id", "run-42",
               "--output", str(output))
    assert code == 0

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["id"] == "cred-001"
    assert data["password"] == "hunter2"
    assert data["run_id"] == "run-42"

    with Pool(db_path) as pool:
        assert pool.get("cred-001").is_locked()


def test_scan_with_no_match_exits_one(add_one, run):
    add_one()
    assert run("scan", "--env", "nowhere", "--select-via", "claude") == 1


def test_scan_reports_a_failed_selection(add_one, run, monkeypatch):
    from saddlebag.selector import SelectionError

    add_one()

    def explode(req, cands, agent):
        raise SelectionError("agent went rogue")

    monkeypatch.setattr(cli, "select", explode)
    assert run("scan", "--env", "staging", "--select-via", "claude") == 1


# -- acquire / release ------------------------------------------------------


def test_acquire_emits_the_password_to_stdout_on_output_json(add_one, run, capsys):
    add_one()
    assert run("acquire", "cred-001", "--output-json") == 0
    assert json.loads(out(capsys))["password"] == "hunter2"


def test_acquire_a_leased_credential_exits_one(add_one, run):
    add_one()
    run("acquire", "cred-001")
    assert run("acquire", "cred-001") == 1


def test_acquire_unknown_credential_exits_one(add_one, run):
    add_one()
    assert run("acquire", "cred-999") == 1


def test_acquire_when_the_store_lost_the_password_exits_one(add_one, run, store):
    add_one()
    store.delete("cred-001")
    assert run("acquire", "cred-001") == 1


def test_release_by_lease_id(add_one, run, tmp_path, db_path):
    add_one()
    output = tmp_path / "credential.json"
    run("acquire", "cred-001", "--output", str(output))
    lease_id = json.loads(output.read_text(encoding="utf-8"))["lease_id"]

    assert run("release", "--lease-id", lease_id) == 0
    with Pool(db_path) as pool:
        assert not pool.get("cred-001").is_locked()


def test_release_by_run_id(add_one, run, capsys):
    add_one()
    add_one(username="b@staging.com")
    run("acquire", "cred-001", "--run-id", "run-42")
    run("acquire", "cred-002", "--run-id", "run-42")

    assert run("release", "--run-id", "run-42") == 0
    assert "released 2 credentials" in out(capsys)


def test_release_requires_a_selector(run):
    assert run("release") == 2


def test_release_of_nothing_is_not_an_error(run):
    """CI cleanup must be idempotent — releasing twice cannot fail the build."""
    assert run("release", "--lease-id", "ghost") == 0


# -- expire / doctor --------------------------------------------------------


def test_expire_reclaims_a_stale_lease(add_one, run, capsys, db_path):
    add_one()
    run("acquire", "cred-001", "--ttl", "1")

    # Reach past the TTL rather than sleeping.
    with Pool(db_path) as pool:
        pool._conn.execute("UPDATE credentials SET expires_at = 0 WHERE id = 'cred-001'")

    assert run("expire") == 0
    assert "expired 1 stale lease" in out(capsys)


def test_doctor_reports_a_stale_lease(add_one, run, capsys, db_path):
    """doctor and expire must agree: anything doctor calls stale, expire reclaims."""
    add_one()
    run("acquire", "cred-001", "--ttl", "1")
    with Pool(db_path) as pool:
        pool._conn.execute("UPDATE credentials SET expires_at = 0 WHERE id = 'cred-001'")

    run("doctor", "--json")
    assert json.loads(out(capsys))["stale"] == ["cred-001"]

    assert run("expire") == 0
    assert "expired 1 stale lease" in out(capsys)


def test_doctor_is_clean_on_a_healthy_pool(add_one, run, capsys):
    add_one()
    assert run("doctor", "--json") == 0
    assert json.loads(out(capsys))["problems"] == []


def test_doctor_flags_a_credential_whose_password_vanished(add_one, run, capsys, store):
    add_one()
    store.delete("cred-001")

    assert run("doctor", "--json") == 1
    assert json.loads(out(capsys))["orphans"] == ["cred-001"]


def test_doctor_reports_an_unavailable_store_instead_of_dying(run, monkeypatch, capsys):
    from saddlebag.store import StoreUnavailableError

    def explode(backend=None):
        raise StoreUnavailableError("no secret store available: set VAULT_ADDR")

    monkeypatch.setattr(cli, "open_store", explode)
    assert run("doctor", "--json") == 1
    report = json.loads(out(capsys))
    assert report["store"] is None
    assert "no secret store" in report["problems"][0]


def test_an_unavailable_store_fails_other_commands(run, monkeypatch):
    from saddlebag.store import StoreUnavailableError

    def explode(backend=None):
        raise StoreUnavailableError("nope")

    monkeypatch.setattr(cli, "open_store", explode)
    assert run("add", "--username", "a@x.com", "--env", "staging",
               "--password-stdin", stdin="hunter2") == 1


# -- remove -----------------------------------------------------------------


def test_remove_deletes_metadata_and_password(add_one, run, db_path, store):
    add_one()
    assert run("remove", "cred-001") == 0
    with Pool(db_path) as pool:
        assert pool.get("cred-001") is None
    assert store.get("cred-001") is None


def test_remove_refuses_a_leased_credential(add_one, run, store):
    add_one()
    run("acquire", "cred-001")
    assert run("remove", "cred-001") == 1
    assert store.get("cred-001") == "hunter2"


def test_remove_force_overrides_the_lease(add_one, run):
    add_one()
    run("acquire", "cred-001")
    assert run("remove", "cred-001", "--force") == 0


def test_remove_unknown_credential_exits_one(run):
    assert run("remove", "cred-404") == 1


def _sel():
    from saddlebag.selector import Selection

    return Selection(selected="cred-001", reason="only match")
