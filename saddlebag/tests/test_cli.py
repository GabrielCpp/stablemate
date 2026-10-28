"""The thin client: what it sends, what it prints, and how exec and serve behave."""

from __future__ import annotations

import json
import importlib.metadata
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from saddlebag import browser, cli, daemon, verbs
from saddlebag.models import Secret

from conftest import FakeBackend, RecordingSession, Running

PASSWORD = "hunter2-pw"
Run = Callable[..., int]


def seed(running: Running) -> None:
    running.vault.create(Secret("login", "gab", "A login", "LOGIN_PASSWORD", frozenset({("environment", "local")})))
    running.vault.set_value("login", "password", PASSWORD)


def test_create_set_and_list_round_trip(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "create", "login", "--username", "gab", "--description", "A login", "--var", "LOGIN_PASSWORD", "--tag", "environment=local") == 0
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
    out = capsys.readouterr().out
    assert "stored 10 characters" in out
    assert PASSWORD not in out
    assert running.vault.data["login"] == {"password": PASSWORD}
    assert run("list", "--tag", "environment=local") == 0
    table = capsys.readouterr().out
    assert "login" in table and "LOGIN_PASSWORD" in table and "environment=local" in table and PASSWORD not in table


def test_list_json_prints_the_daemons_result(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("list", "--json") == 0
    assert json.loads(capsys.readouterr().out)["secrets"][0]["name"] == "login"


def test_tags_prints_key_value_lines(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("tags") == 0
    assert capsys.readouterr().out.splitlines() == ["environment=local"]


def test_a_malformed_tag_is_a_usage_error(running: Running, run: Run) -> None:
    assert run("list", "--tag", "nonsense") == 2


def test_an_empty_stdin_value_is_a_usage_error(running: Running, run: Run) -> None:
    seed(running)
    assert run("secret", "set", "login", stdin="  \n") == 2
    assert running.vault.data["login"] == {"password": PASSWORD}


def test_a_daemon_error_exits_one_with_its_message(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "remove", "ghost") == 1
    assert "no such secret: ghost" in capsys.readouterr().err


def test_a_missing_daemon_exits_one_and_says_how_to_start_it(daemon_path: Path, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("list") == 1
    assert "saddlebag serve" in capsys.readouterr().err


def test_unset_tag_untag_and_remove_reach_the_vault(running: Running, run: Run) -> None:
    seed(running)
    assert run("secret", "tag", "login", "roles=admin") == 0
    assert ("roles", "admin") in running.vault.metadata["login"].tags
    assert run("secret", "untag", "login", "roles=admin") == 0
    assert ("roles", "admin") not in running.vault.metadata["login"].tags
    assert run("secret", "unset", "login", "--field", "password") == 0
    assert running.vault.data["login"] == {}
    assert run("secret", "remove", "login") == 0
    assert running.vault.names() == []


def test_fill_prints_a_count_and_never_the_value(
    running: Running, run: Run, fake_browser: tuple[browser.Target, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    seed(running)
    assert run("fill", "login", "--selector", "#pw") == 0
    captured = capsys.readouterr()
    assert "filled 10 characters into #pw on https://github.com/login" in captured.out
    assert PASSWORD not in captured.out + captured.err
    assert RecordingSession.last is not None and RecordingSession.last.typed == PASSWORD


def test_fill_json_reports_the_character_count(running: Running, run: Run, fake_browser: tuple[browser.Target, ...], capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("fill", "login", "--selector", "#pw", "--json") == 0
    assert json.loads(capsys.readouterr().out)["characters"] == 10


def test_doctor_exits_one_when_a_secret_has_no_value(running: Running, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    running.vault.create(Secret("empty"))
    assert run("doctor") == 1
    assert "empty" in capsys.readouterr().out
    assert run("doctor", "--json") == 1
    assert json.loads(capsys.readouterr().out)["secrets_without_value"] == ["empty"]


class ExecCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []

    def __call__(self, file: str, argv: list[str], env: dict[str, str]) -> None:
        self.calls.append((file, argv, env))


@pytest.fixture
def execvpe(monkeypatch: pytest.MonkeyPatch) -> ExecCapture:
    capture = ExecCapture()
    monkeypatch.setattr(os, "execvpe", capture)
    monkeypatch.setattr(cli, "_on_terminal", lambda: True)
    return capture


def test_exec_runs_the_command_with_the_secrets_in_its_environment(running: Running, run: Run, execvpe: ExecCapture, monkeypatch: pytest.MonkeyPatch) -> None:
    seed(running)
    monkeypatch.setenv("KEEP_ME", "yes")
    assert run("exec", "--tag", "environment=local", "--", "sh", "-c", "echo hi") == 0
    [(file, argv, env)] = execvpe.calls
    assert (file, argv) == ("sh", ["sh", "-c", "echo hi"])
    assert env["LOGIN_PASSWORD"] == PASSWORD
    assert env["KEEP_ME"] == "yes"


def test_exec_binds_an_explicit_field(running: Running, run: Run, execvpe: ExecCapture) -> None:
    seed(running)
    assert run("exec", "--env", "WHO=login.username", "--env", "PW=login", "--", "true") == 0
    [(_, _, env)] = execvpe.calls
    assert env["WHO"] == "gab"
    assert env["PW"] == PASSWORD


def test_exec_does_not_run_the_command_when_the_daemon_refuses(running: Running, run: Run, execvpe: ExecCapture, capsys: pytest.CaptureFixture[str]) -> None:
    running.vault.create(Secret("nameless", tags=frozenset({("environment", "local")})))
    assert run("exec", "--tag", "environment=local", "--", "true") == 1
    assert execvpe.calls == []
    assert "nameless" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [("exec", "--tag", "environment=local"), ("exec", "--", "true"), ("exec", "--env", "BAD", "--", "true")],
)
def test_exec_usage_errors_exit_two(running: Running, run: Run, execvpe: ExecCapture, argv: tuple[str, ...]) -> None:
    assert run(*argv) == 2
    assert execvpe.calls == []


def test_exec_reports_a_command_that_cannot_start(running: Running, run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)

    def missing(file: str, argv: list[str], env: dict[str, str]) -> None:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(os, "execvpe", missing)
    monkeypatch.setattr(cli, "_on_terminal", lambda: True)
    assert run("exec", "--tag", "environment=local", "--", "nope") == 127
    assert "cannot run nope" in capsys.readouterr().err


def test_exec_off_a_terminal_masks_the_secret_in_both_streams(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    script = 'printf "out %s\\n" "$LOGIN_PASSWORD"; printf "err %s\\n" "$LOGIN_PASSWORD" >&2'
    assert run("exec", "--tag", "environment=local", "--", "sh", "-c", script) == 0
    captured = capsys.readouterr()
    assert captured.out == "out [REDACTED]\n"
    assert captured.err == "err [REDACTED]\n"


def test_exec_off_a_terminal_returns_the_commands_exit_code(running: Running, run: Run) -> None:
    seed(running)
    assert run("exec", "--tag", "environment=local", "--", "sh", "-c", "exit 3") == 3


def test_exec_off_a_terminal_leaves_a_bound_username_readable(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    script = 'printf "%s %s\\n" "$WHO" "$PW"'
    assert run("exec", "--env", "WHO=login.username", "--env", "PW=login", "--", "sh", "-c", script) == 0
    captured = capsys.readouterr()
    assert captured.out == "gab [REDACTED]\n"
    assert "WHO" not in captured.err


def test_exec_off_a_terminal_warns_about_a_secret_too_short_to_mask(running: Running, run: Run, execvpe: ExecCapture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "_on_terminal", lambda: False)
    running.vault.create(Secret("pin", var="PIN", tags=frozenset({("environment", "local")})))
    running.vault.set_value("pin", "password", "1234")
    assert run("exec", "--tag", "environment=local", "--", "true") == 0
    assert "warning: PIN is shorter than 8 characters" in capsys.readouterr().err
    [(_, _, env)] = execvpe.calls
    assert env["PIN"] == "1234"


def test_exec_off_a_terminal_reports_a_command_that_cannot_start(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("exec", "--tag", "environment=local", "--", "saddlebag-no-such-command") == 127
    assert "cannot run saddlebag-no-such-command" in capsys.readouterr().err


def test_serve_refuses_when_vault_token_is_in_the_environment(run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("VAULT_TOKEN", "root")
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    assert run("serve", stdin="root\n") == 2
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "VAULT_TOKEN" in err
    assert "root\n" not in err


def test_serve_refuses_an_empty_token_on_stdin(run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    assert run("serve", stdin="\n") == 2
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "empty Vault token" in err


def test_serve_refuses_without_a_vault_address(run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    assert run("serve", stdin="root\n") == 2
    assert "VAULT_ADDR" in capsys.readouterr().err


def test_serve_hands_the_stdin_token_to_vault(run: Run, monkeypatch: pytest.MonkeyPatch, daemon_path: Path) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    seen: dict[str, object] = {}

    class Store:
        pass

    def connect(addr: str, token: str) -> Store:
        seen.update(addr=addr, token=token)
        return Store()

    def serve(store: object, *, socket_path: Path, browser_endpoint: str, stop: object, token_source: str | None = None) -> None:
        seen.update(path=socket_path, cdp=browser_endpoint)

    monkeypatch.setattr("saddlebag.vault.VaultStore", connect)
    monkeypatch.setattr(daemon, "serve", serve)
    assert run("serve", "--vault-addr", "http://vault.example.com:8200", "--cdp", "http://127.0.0.1:9333", stdin="  s.token  \n") == 0
    assert seen == {"addr": "http://vault.example.com:8200", "token": "s.token", "path": daemon_path, "cdp": "http://127.0.0.1:9333"}


def test_version_reports_the_installed_distribution(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert importlib.metadata.version("stablemate-saddlebag") in capsys.readouterr().out


def test_the_keyring_route_creates_sets_and_lists_without_the_value(
    keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("secret", "create", "login", "--username", "gab", "--var", "LOGIN_PASSWORD", "--tag", "environment=local") == 0
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
    assert PASSWORD not in capsys.readouterr().out
    assert run("list", "--json") == 0
    out = capsys.readouterr().out
    assert PASSWORD not in out
    [entry] = json.loads(out)["secrets"]
    assert entry["fields"] == ["password"]
    assert entry["tags"] == [["environment", "local"]]
    assert keyring_route.items == {("stablemate-saddlebag", "login/password"): PASSWORD}


def test_the_keyring_route_filters_by_tag(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "create", "local-login", "--tag", "environment=local") == 0
    assert run("secret", "create", "staging-login", "--tag", "environment=staging") == 0
    capsys.readouterr()
    assert run("list", "--tag", "environment=local", "--json") == 0
    assert [s["name"] for s in json.loads(capsys.readouterr().out)["secrets"]] == ["local-login"]


def test_the_keyring_route_fills_a_browser_field(
    keyring_route: FakeBackend, run: Run, fake_browser: tuple[browser.Target, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("secret", "create", "login") == 0
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
    capsys.readouterr()
    assert run("fill", "login", "--selector", "#pw") == 0
    captured = capsys.readouterr()
    assert "filled 10 characters into #pw on https://github.com/login" in captured.out
    assert PASSWORD not in captured.out + captured.err
    assert RecordingSession.last is not None and RecordingSession.last.typed == PASSWORD


def test_the_keyring_route_refuses_a_value_for_a_missing_secret(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "set", "ghost", stdin=PASSWORD + "\n") == 1
    captured = capsys.readouterr()
    assert "no such secret: ghost" in captured.err
    assert PASSWORD not in captured.out + captured.err
    assert keyring_route.items == {}


def test_a_locked_keyring_exits_one_with_the_unlock_hint(
    keyring_route: FakeBackend, run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import keyring.errors

    def locked(service: str, username: str) -> str | None:
        raise keyring.errors.KeyringLocked("locked")

    assert run("secret", "create", "login") == 0
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
    monkeypatch.setattr(keyring_route, "get_password", locked)
    capsys.readouterr()
    assert run("fill", "login", "--selector", "#pw") == 1
    assert "the OS keyring is locked" in capsys.readouterr().err


def make_login(run: Run, *extra: str) -> None:
    assert run("secret", "create", "login", "--username", "gab", "--var", "LOGIN_PASSWORD", "--tag", "environment=local", *extra) == 0
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0


def test_the_keyring_route_exec_fills_the_tagged_var(
    keyring_route: FakeBackend, run: Run, execvpe: ExecCapture, capsys: pytest.CaptureFixture[str]
) -> None:
    make_login(run)
    capsys.readouterr()
    assert run("exec", "--tag", "environment=local", "--", "true") == 0
    [(_, _, env)] = execvpe.calls
    assert env["LOGIN_PASSWORD"] == PASSWORD
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out + captured.err


def test_the_keyring_route_exec_binds_explicit_fields(keyring_route: FakeBackend, run: Run, execvpe: ExecCapture) -> None:
    make_login(run)
    assert run("exec", "--env", "WHO=login.username", "--env", "PW=login", "--", "true") == 0
    [(_, _, env)] = execvpe.calls
    assert env["WHO"] == "gab"
    assert env["PW"] == PASSWORD


def test_the_keyring_route_tags_lists_the_pairs_in_use(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    make_login(run)
    capsys.readouterr()
    assert run("tags") == 0
    assert capsys.readouterr().out.splitlines() == ["environment=local"]


def test_the_keyring_route_tag_untag_unset_and_remove(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    make_login(run)

    def listed() -> list[dict[str, Any]]:
        capsys.readouterr()
        assert run("list", "--json") == 0
        return json.loads(capsys.readouterr().out)["secrets"]

    assert run("secret", "tag", "login", "roles=admin") == 0
    assert ["roles", "admin"] in listed()[0]["tags"]
    assert run("secret", "untag", "login", "roles=admin") == 0
    assert ["roles", "admin"] not in listed()[0]["tags"]
    assert run("secret", "unset", "login", "--field", "password") == 0
    assert listed()[0]["fields"] == []
    assert list(keyring_route.items) == []
    assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
    assert list(keyring_route.items) == [("stablemate-saddlebag", "login/password")]
    assert run("secret", "remove", "login") == 0
    assert listed() == []
    assert list(keyring_route.items) == []


def test_doctor_in_keyring_mode_reports_a_healthy_store(
    keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    make_login(run)
    capsys.readouterr()
    assert run("doctor") == 0
    out = capsys.readouterr().out
    assert "backend: keyring" in out
    assert "route: in-process" in out
    assert "store reachable: yes" in out
    assert "orphan keyring items: none" in out
    assert PASSWORD not in out


def test_doctor_in_keyring_mode_exits_one_for_a_secret_without_a_value(
    keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    assert run("secret", "create", "empty") == 0
    capsys.readouterr()
    assert run("doctor") == 1
    assert "secrets without a stored value: empty" in capsys.readouterr().out


def test_doctor_in_keyring_mode_lists_an_orphan_and_still_passes(
    keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    make_login(run)
    keyring_route.items[("stablemate-saddlebag", "ghost/password")] = "x"
    capsys.readouterr()
    assert run("doctor") == 0
    assert "orphan keyring items: ghost/password" in capsys.readouterr().out


def test_doctor_in_keyring_mode_reports_drift(
    keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    make_login(run)
    del keyring_route.items[("stablemate-saddlebag", "login/password")]
    capsys.readouterr()
    assert run("doctor") == 1
    assert "warning: the catalogue lists a value for login/password that the keyring no longer holds" in capsys.readouterr().out
    assert run("doctor", "--json") == 1
    assert json.loads(capsys.readouterr().out)["missing_items"] == ["login/password"]


def test_doctor_over_the_daemon_keeps_the_legacy_key(running: Running, run: Run, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(verbs, "VAULT_TOKEN_FILE", tmp_path / "none")
    running.vault.create(Secret("empty"))
    assert run("doctor", "--json") == 1
    result = json.loads(capsys.readouterr().out)
    assert result["vault_authenticated"] is True
    assert result["backend"] == "vault"
    assert run("doctor") == 1
    out = capsys.readouterr().out
    assert "route: socket " in out and "(daemon " in out
    assert "orphan keyring items" not in out


def test_metadata_is_created_edited_dropped_and_listed(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "create", "qa_admin", "--username", "qa@example.com", "--meta", "phone=+15555550100", "--meta", "role=admin") == 0
    assert running.vault.metadata["qa_admin"].metadata == {"phone": "+15555550100", "role": "admin"}
    assert run("secret", "meta", "qa_admin", "phone=+15555550199", "team=blue") == 0
    assert "updated metadata of qa_admin" in capsys.readouterr().out
    assert run("secret", "unmeta", "qa_admin", "team") == 0
    assert "dropped metadata of qa_admin" in capsys.readouterr().out
    assert run("list") == 0
    table = capsys.readouterr().out
    assert "METADATA" in table and "phone=+15555550199,role=admin" in table
    assert run("list", "--json") == 0
    [entry] = json.loads(capsys.readouterr().out)["secrets"]
    assert entry["metadata"] == {"phone": "+15555550199", "role": "admin"}


def test_unmeta_of_an_unknown_key_is_an_error(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("secret", "unmeta", "login", "nope") == 1
    assert "login has no metadata nope" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ("secret", "create", "x", "--meta", "a.b=1"),
        ("secret", "create", "x", "--meta", "nonsense"),
        ("secret", "meta", "login", "a.b=1"),
    ],
)
def test_a_bad_metadata_item_is_a_usage_error(running: Running, run: Run, argv: tuple[str, ...]) -> None:
    seed(running)
    assert run(*argv) == 2


def test_a_dotted_key_is_refused_by_unmeta(running: Running, run: Run) -> None:
    seed(running)
    assert run("secret", "unmeta", "login", "a.b") == 1


def test_a_value_cannot_be_stored_in_a_meta_field(running: Running, run: Run) -> None:
    seed(running)
    assert run("secret", "set", "login", "--field", "meta.k", stdin="v\n") == 2


def test_exec_binds_metadata_unmasked(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    ok = run("secret", "meta", "login", "phone=+15555550199")
    assert ok == 0
    script = 'printf "%s %s\\n" "$QA_PHONE" "$PW"'
    assert run("exec", "--env", "QA_PHONE=login.meta.phone", "--env", "PW=login", "--", "sh", "-c", script) == 0
    captured = capsys.readouterr()
    assert captured.out == "+15555550199 [REDACTED]\n"
    assert "QA_PHONE" not in captured.err


def test_exec_sets_a_metadata_variable_without_a_short_value_warning(running: Running, run: Run, execvpe: ExecCapture, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_on_terminal", lambda: False)
    running.vault.create(Secret("qa_admin", metadata={"role": "a"}))
    assert run("exec", "--env", "ROLE=qa_admin.meta.role", "--", "true") == 0
    [(_, _, env)] = execvpe.calls
    assert env["ROLE"] == "a"
    assert "warning" not in capsys.readouterr().err


def test_exec_names_the_missing_metadata_key(running: Running, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    seed(running)
    assert run("exec", "--env", "X=login.meta.phone", "--", "true") == 1
    assert "saddlebag secret meta login phone=..." in capsys.readouterr().err


def test_fill_types_a_metadata_value(running: Running, run: Run, fake_browser: tuple[browser.Target, ...]) -> None:
    running.vault.create(Secret("qa_admin", metadata={"phone": "+15555550199"}))
    assert run("fill", "qa_admin", "--field", "meta.phone", "--selector", "#phone") == 0
    assert RecordingSession.last is not None and RecordingSession.last.typed == "+15555550199"


def test_the_keyring_route_carries_metadata(keyring_route: FakeBackend, run: Run, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("secret", "create", "qa_admin", "--meta", "phone=+1") == 0
    assert run("secret", "meta", "qa_admin", "role=admin") == 0
    capsys.readouterr()
    assert run("list", "--json") == 0
    [entry] = json.loads(capsys.readouterr().out)["secrets"]
    assert entry["metadata"] == {"phone": "+1", "role": "admin"}
    assert keyring_route.items == {}
