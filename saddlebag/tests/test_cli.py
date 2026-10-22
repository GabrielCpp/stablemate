"""The thin client: what it sends, what it prints, and how exec and serve behave."""

from __future__ import annotations

import json
import importlib.metadata
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag import browser, cli, daemon
from saddlebag.models import Secret

from conftest import RecordingSession, Running

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
    monkeypatch.setattr(daemon, "VAULT_TOKEN_FILE", tmp_path / "none")
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
    assert run("exec", "--tag", "environment=local", "--", "nope") == 127
    assert "cannot run nope" in capsys.readouterr().err


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

    def serve(store: object, *, socket_path: Path, browser_endpoint: str, stop: object) -> None:
        seen.update(path=socket_path, cdp=browser_endpoint)

    monkeypatch.setattr(cli, "VaultStore", connect)
    monkeypatch.setattr(daemon, "serve", serve)
    assert run("serve", "--vault-addr", "http://vault.example.com:8200", "--cdp", "http://127.0.0.1:9333", stdin="  s.token  \n") == 0
    assert seen == {"addr": "http://vault.example.com:8200", "token": "s.token", "path": daemon_path, "cdp": "http://127.0.0.1:9333"}


def test_version_reports_the_installed_distribution(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert importlib.metadata.version("stablemate-saddlebag") in capsys.readouterr().out
