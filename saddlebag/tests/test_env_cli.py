"""The `saddlebag env` CLI: the kind-by-channel rule, the leak-proof reads, render."""

from __future__ import annotations

import io
import json
import stat
from pathlib import Path

import pytest

from saddlebag import cli
from saddlebag.db import Pool

SECRET = "AIzaSy-REAL-KEY"


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, store):
    """Never the real keyring — not in this test, not on a developer's laptop."""
    monkeypatch.setattr(cli, "open_store", lambda backend=None: store)
    return store


@pytest.fixture(autouse=True)
def no_inferred_project(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "infer_project", lambda: None)


@pytest.fixture
def run(db_path: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    def _run(*argv: str, stdin: str | None = None) -> int:
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            cli.main(["--db", str(db_path), *argv])
        return exc.value.code

    return _run


@pytest.fixture
def target(tmp_path: Path) -> Path:
    return tmp_path / "web" / ".env.local"


@pytest.fixture
def web(run, target: Path):
    """The environment from the incident: two config keys and one real secret."""
    run("env", "add", "web-local", "--env", "local", "--target", str(target))
    run("env", "set", "web-local", "VITE_FIREBASE_PROJECT_ID=acme")
    run("env", "set", "web-local", "VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099")
    run("env", "set", "web-local", "VITE_FIREBASE_API_KEY", "--secret-stdin", stdin=SECRET)
    return "web-local"


def out(capsys) -> str:
    return capsys.readouterr().out


# -- the channel decides the kind ---------------------------------------------


def test_a_value_on_argv_is_config_and_lands_in_the_pool_db(run, db_path, store):
    """It is already in the process table and the shell history. Calling it a secret
    would be a lie about its exposure."""
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "VITE_FIREBASE_PROJECT_ID=acme") == 0

    with Pool(db_path) as pool:
        entry = pool.env_get_entry("env-001", "VITE_FIREBASE_PROJECT_ID")
    assert (entry.kind, entry.value) == ("config", "acme")
    assert store.secrets == {}


def test_a_value_on_stdin_is_a_secret_and_never_reaches_the_pool_db(run, db_path, store):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "API_KEY", "--secret-stdin", stdin=SECRET) == 0

    with Pool(db_path) as pool:
        entry = pool.env_get_entry("env-001", "API_KEY")
    assert (entry.kind, entry.value) == ("secret", None)
    assert store.secrets == {"env-001/API_KEY": SECRET}


def test_from_credential_is_a_credential_ref_and_stores_nothing(run, db_path, store):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "TEST_USER_PASSWORD",
               "--from-credential", "cred-007:password") == 0

    with Pool(db_path) as pool:
        entry = pool.env_get_entry("env-001", "TEST_USER_PASSWORD")
    assert (entry.kind, entry.cred_ref) == ("credential-ref", "cred-007:password")
    assert store.secrets == {}


def test_set_with_no_value_source_is_a_usage_error(run):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "API_KEY") == 2


def test_set_rejects_a_malformed_credential_ref(run):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "K", "--from-credential", "cred-007:token") == 2


def test_set_can_annotate_a_key_without_supplying_a_value(run, db_path):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "set", "web-local", "SENTRY_DSN", "--optional",
               "--note", "only needed in staging") == 0

    with Pool(db_path) as pool:
        entry = pool.env_get_entry("env-001", "SENTRY_DSN")
    assert (entry.kind, entry.required, entry.note) == ("pending", False, "only needed in staging")


def test_demoting_a_secret_to_config_drops_the_stored_value(run, store, web):
    """Otherwise the old secret lingers in the keyring, referenced by nothing."""
    assert store.secrets == {"env-001/VITE_FIREBASE_API_KEY": SECRET}
    run("env", "set", web, "VITE_FIREBASE_API_KEY=publishable-after-all")
    assert store.secrets == {}


def test_unset_removes_the_key_and_its_secret(run, store, web, db_path):
    assert run("env", "unset", web, "VITE_FIREBASE_API_KEY") == 0
    assert store.secrets == {}
    with Pool(db_path) as pool:
        assert pool.env_get_entry("env-001", "VITE_FIREBASE_API_KEY") is None


# -- import -------------------------------------------------------------------


def test_import_from_an_env_example_takes_keys_and_never_values(run, tmp_path, capsys,
                                                                db_path, store):
    example = tmp_path / ".env.example"
    example.write_text("VITE_FIREBASE_API_KEY=placeholder\nVITE_FIREBASE_PROJECT_ID=\n",
                       encoding="utf-8")
    run("env", "add", "web-local", "--env", "local")

    assert run("env", "import", "web-local", "--from", str(example)) == 0
    assert "every key is pending" in out(capsys)

    with Pool(db_path) as pool:
        entries = pool.env_get("env-001").entries
    assert [e.key for e in entries] == ["VITE_FIREBASE_API_KEY", "VITE_FIREBASE_PROJECT_ID"]
    assert {e.kind for e in entries} == {"pending"}
    assert all(e.value is None for e in entries)  # 'placeholder' was never stored
    assert store.secrets == {}


def test_reimporting_does_not_clobber_a_supplied_value(run, tmp_path, db_path):
    example = tmp_path / ".env.example"
    example.write_text("PROJECT_ID=\n", encoding="utf-8")
    run("env", "add", "web-local", "--env", "local")
    run("env", "import", "web-local", "--from", str(example))
    run("env", "set", "web-local", "PROJECT_ID=acme")

    assert run("env", "import", "web-local", "--from", str(example)) == 0
    with Pool(db_path) as pool:
        assert pool.env_get_entry("env-001", "PROJECT_ID").value == "acme"


def test_import_into_an_unknown_environment_exits_one(run, tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("K=\n", encoding="utf-8")
    assert run("env", "import", "nope", "--from", str(example)) == 1


# -- the manifest: package, move, reconstitute --------------------------------


def test_export_then_import_reconstitutes_the_environment_on_a_fresh_host(
    run, web, tmp_path, capsys, monkeypatch, store,
):
    """§8: the manifest carries the configuration, the store carries the secrets.
    A fresh pool + the manifest + the store is the whole environment back."""
    out_path = tmp_path / "env" / "web-local.yaml"
    assert run("env", "export", web, "--output", str(out_path)) == 0
    assert SECRET not in out_path.read_text(encoding="utf-8")

    fresh = tmp_path / "fresh.db"  # a container that has never seen this repo
    with pytest.raises(SystemExit) as exc:
        cli.main(["--db", str(fresh), "env", "import", "web-local", "--from", str(out_path)])
    assert exc.value.code == 0

    with Pool(fresh) as pool:
        environment = pool.env_by_name("web-local")
    assert environment.target.endswith(".env.local")
    assert {e.key: e.kind for e in environment.entries} == {
        "VITE_FIREBASE_PROJECT_ID": "config",
        "VITE_FIREBASE_AUTH_EMULATOR_HOST": "config",
        "VITE_FIREBASE_API_KEY": "secret",
    }
    # The secret came from the store, which travelled separately — as designed.
    assert store.get(environment.store_key("VITE_FIREBASE_API_KEY")) == SECRET


def test_export_to_stdout_cannot_emit_a_secret(run, web, capsys):
    assert run("env", "export", web) == 0
    assert SECRET not in out(capsys)


def test_a_manifest_carrying_a_secret_value_is_refused(run, tmp_path):
    poisoned = tmp_path / "poisoned.yaml"
    poisoned.write_text(
        "name: web-local\nenv: local\n"
        "entries:\n  - key: API_KEY\n    kind: secret\n    value: sk_live_oops\n",
        encoding="utf-8",
    )
    assert run("env", "import", "web-local", "--from", str(poisoned)) == 1


# -- list / show: structurally incapable of leaking ---------------------------


def test_show_prints_config_in_the_clear_and_a_secret_as_set(run, web, capsys):
    assert run("env", "show", web) == 0
    printed = out(capsys)

    assert "127.0.0.1:9099" in printed      # config is the point of config
    assert SECRET not in printed
    assert "<set>" in printed


def test_show_json_never_carries_a_secret(run, web, capsys):
    assert run("env", "show", web, "--json") == 0
    payload = out(capsys)
    assert SECRET not in payload

    entries = {e["key"]: e for e in json.loads(payload)["entries"]}
    assert entries["VITE_FIREBASE_API_KEY"]["value"] is None


def test_list_scopes_by_project(run, capsys, monkeypatch):
    run("env", "add", "web-local", "--env", "local", "--project", "acme")
    run("env", "add", "api-local", "--env", "local", "--project", "other-repo")

    monkeypatch.setattr(cli, "infer_project", lambda: "acme")
    assert run("env", "list", "--json") == 0
    assert [e["name"] for e in json.loads(out(capsys))] == ["web-local"]

    assert run("env", "list", "--all-projects", "--json") == 0
    assert len(json.loads(out(capsys))) == 2


# -- render -------------------------------------------------------------------


def test_render_writes_the_file_0600_and_prints_only_the_path(run, web, target, capsys):
    assert run("env", "render", web) == 0

    assert out(capsys).strip() == str(target)     # the path, never the contents
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text(encoding="utf-8") == (
        "VITE_FIREBASE_PROJECT_ID=acme\n"
        "VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099\n"
        f"VITE_FIREBASE_API_KEY={SECRET}\n"
    )


def test_render_names_the_exact_keys_a_human_must_supply(run, web, target, caplog):
    """The escalation setup_fix makes: not 'unfixable', but 'unfixable, and here is
    precisely what is missing'."""
    run("env", "set", web, "VITE_STRIPE_PUBLISHABLE_KEY", "--note", "ask the ops team")

    assert run("env", "render", web) == 1
    assert "VITE_STRIPE_PUBLISHABLE_KEY" in caplog.text
    assert not target.exists()  # nothing is written until everything resolves


def test_render_of_a_config_only_environment_needs_no_store(run, tmp_path, monkeypatch,
                                                            capsys):
    """§7: on a container with no keyring and no Vault, this still renders."""
    from saddlebag.store import StoreUnavailableError

    def explode(backend=None):
        raise StoreUnavailableError("no secret store available")

    monkeypatch.setattr(cli, "open_store", explode)

    target = tmp_path / ".env"
    run("env", "add", "cfg", "--env", "local", "--target", str(target))
    run("env", "set", "cfg", "VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099")

    assert run("env", "render", "cfg") == 0
    assert target.read_text(encoding="utf-8") == "VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099\n"


def test_render_leases_a_credential_ref_and_release_frees_it(run, store, web, target, db_path):
    run("add", "--username", "qa@acme.example", "--env", "local", "--password-stdin",
        stdin="hunter2")
    run("env", "set", web, "TEST_USER_PASSWORD", "--from-credential", "cred-001:password")

    assert run("env", "render", web, "--run-id", "run-42") == 0
    assert "TEST_USER_PASSWORD=hunter2" in target.read_text(encoding="utf-8")

    with Pool(db_path) as pool:
        assert pool.get("cred-001").run_id == "run-42"

    # The bookend the workflow already has needs no change to clean up after render.
    assert run("release", "--run-id", "run-42") == 0
    with Pool(db_path) as pool:
        assert not pool.get("cred-001").is_locked()


def test_render_with_no_target_is_a_usage_error(run):
    run("env", "add", "web-local", "--env", "local")
    assert run("env", "render", "web-local") == 2


def test_render_to_json_format(run, tmp_path):
    target = tmp_path / "env.json"
    run("env", "add", "cfg", "--env", "local", "--target", str(target), "--format", "json")
    run("env", "set", "cfg", "HOST=127.0.0.1:9099")

    assert run("env", "render", "cfg") == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {"HOST": "127.0.0.1:9099"}


# -- render --check: the gate --------------------------------------------------


def test_check_writes_nothing_and_reports_the_unrendered_target(run, web, target, capsys):
    assert run("env", "render", web, "--check", "--json") == 1
    report = json.loads(out(capsys))

    assert report["resolvable"] is True     # every key has a value behind it
    assert report["target_exists"] is False  # ...but the file is not there yet
    assert not target.exists()


def test_check_passes_once_the_file_matches(run, web):
    run("env", "render", web)
    assert run("env", "render", web, "--check") == 0


def test_check_reports_drift_by_key_name_only(run, web, target, capsys):
    run("env", "render", web)
    target.write_text(
        target.read_text(encoding="utf-8").replace("acme", "hand-edited"), encoding="utf-8")

    assert run("env", "render", web, "--check", "--json") == 1
    payload = out(capsys)
    assert json.loads(payload)["drift"] == ["VITE_FIREBASE_PROJECT_ID"]
    assert "hand-edited" not in payload
    assert SECRET not in payload


def test_check_takes_no_lease(run, web, db_path):
    run("add", "--username", "qa@x.com", "--env", "local", "--password-stdin", stdin="pw")
    run("env", "set", web, "TEST_USER_PASSWORD", "--from-credential", "cred-001:password")

    run("env", "render", web, "--check", "--run-id", "run-42")
    with Pool(db_path) as pool:
        assert not pool.get("cred-001").is_locked()


# -- doctor -------------------------------------------------------------------


def test_doctor_names_exactly_what_a_human_must_supply(run, web, capsys):
    run("env", "set", web, "VITE_STRIPE_PUBLISHABLE_KEY", "--note", "ask ops")

    assert run("env", "doctor", "--json") == 1
    report = json.loads(out(capsys))
    assert report["environments"][0]["pending"] == ["VITE_STRIPE_PUBLISHABLE_KEY"]


def test_doctor_flags_a_secret_the_store_lost(run, web, store, capsys):
    store.delete("env-001/VITE_FIREBASE_API_KEY")

    assert run("env", "doctor", "--json") == 1
    assert json.loads(out(capsys))["environments"][0]["unset"] == ["VITE_FIREBASE_API_KEY"]


def test_doctor_flags_a_dangling_credential_ref(run, web, capsys):
    run("env", "set", web, "TEST_USER_PASSWORD", "--from-credential", "cred-404:password")

    assert run("env", "doctor", "--json") == 1
    dangling = json.loads(out(capsys))["environments"][0]["dangling"]
    assert "cred-404" in dangling[0]


def test_doctor_is_clean_on_a_healthy_environment(run, web, capsys):
    assert run("env", "doctor", "--json") == 0
    assert json.loads(out(capsys))["problems"] == []


def test_doctor_does_not_open_the_store_for_a_config_only_pool(run, monkeypatch, capsys):
    """A pool of config-only environments is healthy on a host with no keyring, and
    must not be reported as broken there."""
    from saddlebag.store import StoreUnavailableError

    def explode(backend=None):
        raise StoreUnavailableError("no secret store available")

    monkeypatch.setattr(cli, "open_store", explode)
    run("env", "add", "cfg", "--env", "local")
    run("env", "set", "cfg", "HOST=127.0.0.1:9099")

    assert run("env", "doctor", "--json") == 0
    report = json.loads(out(capsys))
    assert report["store"] is None
    assert report["problems"] == []


def test_doctor_reports_an_unavailable_store_when_a_secret_needs_it(run, web, monkeypatch,
                                                                    capsys):
    from saddlebag.store import StoreUnavailableError

    def explode(backend=None):
        raise StoreUnavailableError("no secret store available: set VAULT_ADDR")

    monkeypatch.setattr(cli, "open_store", explode)
    assert run("env", "doctor", "--json") == 1
    assert "no secret store" in json.loads(out(capsys))["problems"][0]


# -- remove -------------------------------------------------------------------


def test_remove_drops_the_environment_and_its_stored_secrets(run, web, store, db_path):
    assert run("env", "remove", web) == 0
    assert store.secrets == {}
    with Pool(db_path) as pool:
        assert pool.env_by_name("web-local") is None


def test_remove_an_unknown_environment_exits_one(run):
    assert run("env", "remove", "nope") == 1
