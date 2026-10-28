"""The masked view of a dotenv, through the daemon and through the keyring route."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from saddlebag.models import Secret

from conftest import FakeBackend, Running

PASSWORD = "hunter2-pw"
Run = Callable[..., int]

DOTENV = """APP_HOST=localhost
APP_PORT=8080
export LOGIN_PASSWORD='hunter2-pw'
DB_URL=postgres://qa:pw@localhost/db
STRIPE_KEY=sk-live-abcdefghijklmnop
GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789
OTHER_SECRET=short
# a comment

PUBLIC_KEY=abc
"""

RULES = {
    "APP_HOST": None,
    "APP_PORT": None,
    "LOGIN_PASSWORD": "held-value",
    "DB_URL": "url-userinfo",
    "STRIPE_KEY": "token-shape",
    "GITHUB_TOKEN": "key-name",
    "OTHER_SECRET": "key-name",
    "PUBLIC_KEY": None,
}


@pytest.fixture
def dotenv_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(DOTENV)
    return path


@pytest.fixture(params=["daemon", "keyring"])
def seeded(request: pytest.FixtureRequest, run: Run, tmp_path: Path) -> Callable[..., None]:
    if request.param == "daemon":
        running: Running = request.getfixturevalue("running")

        def seed_daemon(*extra: str) -> None:
            running.vault.create(Secret("login", "gab", "A login", "LOGIN_PASSWORD", frozenset({("environment", "local")})))
            running.vault.set_value("login", "password", PASSWORD)
            for index, var in enumerate(extra):
                running.vault.create(Secret(f"extra{index}", None, None, var, frozenset()))

        return seed_daemon
    request.getfixturevalue("keyring_route")

    def seed_keyring(*extra: str) -> None:
        assert run("secret", "create", "login", "--username", "gab", "--var", "LOGIN_PASSWORD", "--tag", "environment=local") == 0
        assert run("secret", "set", "login", stdin=PASSWORD + "\n") == 0
        for index, var in enumerate(extra):
            assert run("secret", "create", f"extra{index}", "--var", var) == 0

    return seed_keyring


def test_show_masks_secret_lines_and_keeps_the_rest(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "show", str(dotenv_file)) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "APP_HOST=localhost",
        "APP_PORT=8080",
        "export LOGIN_PASSWORD=[REDACTED]",
        "DB_URL=[REDACTED]",
        "STRIPE_KEY=[REDACTED]",
        "GITHUB_TOKEN=[REDACTED]",
        "OTHER_SECRET=[REDACTED]",
        "# a comment",
        "",
        "PUBLIC_KEY=abc",
        "masked 5 of 8 values",
    ]
    for leaked in (PASSWORD, "sk-live", "pw@", "ghp_", "short"):
        assert leaked not in out


def test_keys_lists_keys_with_their_rule_and_no_values(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "keys", str(dotenv_file)) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == [
        "APP_HOST",
        "APP_PORT",
        "LOGIN_PASSWORD  (secret: held-value)",
        "DB_URL  (secret: url-userinfo)",
        "STRIPE_KEY  (secret: token-shape)",
        "GITHUB_TOKEN  (secret: key-name)",
        "OTHER_SECRET  (secret: key-name)",
        "PUBLIC_KEY",
    ]
    assert "localhost" not in out and PASSWORD not in out


def test_classify_json_carries_every_verdict_in_order(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "classify", str(dotenv_file), "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["file"] == str(dotenv_file)
    assert [(v["key"], v["rule"]) for v in data["verdicts"]] == list(RULES.items())
    assert [v["secret"] for v in data["verdicts"]] == [rule is not None for rule in RULES.values()]


def test_classify_without_json_prints_tab_separated_lines(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "classify", str(dotenv_file)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "APP_HOST\tliteral"
    assert lines[2] == "LOGIN_PASSWORD\tsecret:held-value"


def test_a_registered_var_is_secret_whatever_its_value(seeded: Callable[..., None], run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded("RUNTIME_HANDLE")
    path = tmp_path / "other.env"
    path.write_text("RUNTIME_HANDLE=anything\nPLAIN=anything\n")
    assert run("env", "classify", str(path), "--json") == 0
    verdicts = json.loads(capsys.readouterr().out)["verdicts"]
    assert [(v["key"], v["rule"]) for v in verdicts] == [("RUNTIME_HANDLE", "registered-var"), ("PLAIN", None)]


def test_a_missing_file_exits_one(seeded: Callable[..., None], run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "show", str(tmp_path / "missing.env")) == 1
    assert "missing.env" in capsys.readouterr().err


def test_a_missing_daemon_exits_one(daemon_path: Path, run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "show", str(dotenv_file)) == 1
    assert "saddlebag serve" in capsys.readouterr().err


def test_classify_rejects_malformed_entries(running: Running) -> None:
    assert not running.ask("classify", entries="x").ok
    assert not running.ask("classify", entries=["x"]).ok
    assert not running.ask("classify", entries=[{"value": "v"}]).ok


def test_a_stored_value_is_found_in_its_escaped_form(running: Running) -> None:
    running.vault.create(Secret("s", None, None, None, frozenset()))
    running.vault.set_value("s", "password", "a b$c")
    reply = running.ask("classify", entries=[{"key": "A", "value": "a%20b%24c"}, {"key": "B", "value": "a b$$c"}, {"key": "C", "value": "zz"}])
    assert [v["rule"] for v in reply.result["verdicts"]] == ["held-value", "held-value", None]


def test_short_values_match_by_token_shape_only_above_the_floor(running: Running) -> None:
    reply = running.ask("classify", entries=[{"key": "A", "value": "sk-1"}, {"key": "B", "value": "sk-12345678"}])
    assert [v["rule"] for v in reply.result["verdicts"]] == [None, "token-shape"]


def test_the_backend_fixture_is_used(backend: FakeBackend) -> None:
    assert backend.items == {}


def test_holds_finds_a_stored_value_in_every_written_form_and_never_returns_it(running: Running) -> None:
    value = "pa ss$w0rd&x"
    running.vault.create(Secret("s", "admin-user-1", None, None, frozenset(), metadata={"region": "eu-west-1-x"}))
    running.vault.set_value("s", "password", value)
    texts = [f"echo {value}", "echo pa%20ss%24w0rd%26x", "echo pa+ss%24w0rd%26x", json.dumps({"p": 'pa ss$w0rd&x"'}), "echo pa ss$$w0rd&x"]
    for text in texts:
        reply = running.ask("holds", text=text)
        assert reply.result == {"held": True, "names": ["s"]}
        assert value not in reply.to_json()


def test_holds_is_false_without_a_value_username_metadata_or_a_short_value(running: Running) -> None:
    running.vault.create(Secret("s", "admin-user-1", None, None, frozenset(), metadata={"region": "eu-west-1-x"}))
    running.vault.set_value("s", "password", "pa ss$w0rd&x")
    running.vault.create(Secret("t", None, None, None, frozenset()))
    running.vault.set_value("t", "password", "short1")
    for text in ["echo hello", "echo admin-user-1", "echo eu-west-1-x", "echo short1"]:
        assert running.ask("holds", text=text).result == {"held": False, "names": []}


def test_holds_rejects_a_missing_or_non_string_text(running: Running) -> None:
    assert not running.ask("holds").ok
    assert not running.ask("holds", text=3).ok
