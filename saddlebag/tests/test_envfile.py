"""The .env reader used to import a password one variable at a time."""

from __future__ import annotations

from pathlib import Path

import pytest

from saddlebag import envfile


def write_env(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_plain_assignments(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "USER=admin\nPASSWORD=sekrit\n"))
    assert env == {"USER": "admin", "PASSWORD": "sekrit"}


def test_skips_blanks_and_comments(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "\n# a comment\n\nKEY=value\n  # indented comment\n"))
    assert env == {"KEY": "value"}


def test_strips_an_export_prefix(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "export TOKEN=abc123\n"))
    assert env == {"TOKEN": "abc123"}


def test_strips_matching_quotes_but_keeps_inner_text(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, 'A="  spaced  "\nB=\'single\'\n'))
    assert env == {"A": "  spaced  ", "B": "single"}


def test_a_hash_inside_a_quoted_value_is_preserved(tmp_path: Path):
    """A password may contain '#'; it must not be mistaken for a comment."""
    env = envfile.parse(write_env(tmp_path, 'PW="p#ss word"\n'))
    assert env["PW"] == "p#ss word"


def test_an_equals_sign_inside_a_value_survives(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "TOKEN=a=b=c\n"))
    assert env["TOKEN"] == "a=b=c"


def test_later_assignment_wins(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "K=first\nK=second\n"))
    assert env["K"] == "second"


def test_lines_without_equals_are_ignored(tmp_path: Path):
    env = envfile.parse(write_env(tmp_path, "not an assignment\nK=v\n"))
    assert env == {"K": "v"}


def test_read_var_returns_the_value(tmp_path: Path):
    path = write_env(tmp_path, "ADMIN_PW=hunter2\n")
    assert envfile.read_var(path, "ADMIN_PW") == "hunter2"


def test_read_var_raises_keyerror_for_a_missing_variable(tmp_path: Path):
    path = write_env(tmp_path, "ADMIN_PW=hunter2\n")
    with pytest.raises(KeyError):
        envfile.read_var(path, "NOPE")


def test_read_var_raises_filenotfound_for_a_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        envfile.read_var(tmp_path / "absent.env", "ANY")


def test_read_var_returns_empty_string_for_an_empty_value(tmp_path: Path):
    path = write_env(tmp_path, "EMPTY=\n")
    assert envfile.read_var(path, "EMPTY") == ""
