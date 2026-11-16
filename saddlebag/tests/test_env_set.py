"""`saddlebag env set`, through the daemon and through the keyring route."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from conftest import SEEDED_PASSWORD as PASSWORD

Run = Callable[..., int]

DOTENV = """# local stack
APP_HOST=localhost
export APP_PORT=8080 # http
LOGIN_HINT='hunter2-pw'
GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789
"""


@pytest.fixture
def dotenv_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(DOTENV)
    return path


def test_set_replaces_a_literal_and_leaves_every_other_line(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    capsys.readouterr()
    assert run("env", "set", str(dotenv_file), "APP_PORT", "9090") == 0
    assert capsys.readouterr().out.splitlines() == [f"set APP_PORT in {dotenv_file}"]
    assert dotenv_file.read_text() == DOTENV.replace("APP_PORT=8080", "APP_PORT=9090")


def test_set_appends_a_key_the_file_lacks(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    capsys.readouterr()
    assert run("env", "set", str(dotenv_file), "LOG_LEVEL", "debug info") == 0
    assert capsys.readouterr().out.splitlines() == [f"added LOG_LEVEL in {dotenv_file}"]
    assert dotenv_file.read_text() == DOTENV + "LOG_LEVEL='debug info'\n"


@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("GITHUB_TOKEN", "plain", "key-name"),
        ("LOGIN_HINT", "plain", "held-value"),
        ("APP_HOST", "sk-live-abcdefghijklmnop", "token-shape"),
        ("APP_HOST", "postgres://qa:pw@localhost/db", "url-userinfo"),
        ("LOGIN_PASSWORD", "plain", "registered-var"),
    ],
)
def test_a_secret_line_or_value_is_refused_and_the_file_is_untouched(
    seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str], key: str, value: str, rule: str
) -> None:
    seeded()
    capsys.readouterr()
    assert run("env", "set", str(dotenv_file), key, value) == 2
    captured = capsys.readouterr()
    assert f"{key} is secret ({rule})" in captured.err
    assert dotenv_file.read_text() == DOTENV
    for leaked in (PASSWORD, "ghp_"):
        assert leaked not in captured.out + captured.err


def test_a_value_no_quoting_can_carry_exits_two(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "set", str(dotenv_file), "APP_HOST", "two\nlines") == 2
    assert "cannot span lines" in capsys.readouterr().err
    assert dotenv_file.read_text() == DOTENV


def test_a_bad_key_exits_two(seeded: Callable[..., None], run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "set", str(dotenv_file), "A=B", "x") == 2
    assert "not a dotenv key" in capsys.readouterr().err


def test_a_missing_file_exits_one(seeded: Callable[..., None], run: Run, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    seeded()
    assert run("env", "set", str(tmp_path / "missing.env"), "A", "1") == 1
    assert "missing.env" in capsys.readouterr().err


def test_a_missing_daemon_exits_one_and_writes_nothing(daemon_path: Path, run: Run, dotenv_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("env", "set", str(dotenv_file), "APP_PORT", "9090") == 1
    assert "saddlebag serve" in capsys.readouterr().err
    assert dotenv_file.read_text() == DOTENV
