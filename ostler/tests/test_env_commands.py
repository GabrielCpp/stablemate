"""`ostler env exec` and `ostler env dotenv` against a book with an environment page."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import pytest

from ostler.environments import commands
from ostler.environments import cli as env_cli

from conftest import write
from test_env_inject import FakeSaddlebag
from test_environment_variables import FIXTURE, PAGE


class Executed(Exception):
    def __init__(self, argv: list[str], env: Mapping[str, str]) -> None:
        super().__init__(argv)
        self.argv = argv
        self.env = env


def _execute(argv: list[str], env: Mapping[str, str]) -> NoReturn:
    raise Executed(argv, env)


def _book(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    write(root / PAGE, FIXTURE)
    return root


def test_exec_runs_the_command_under_saddlebag_with_the_literals_in_its_environment(tmp_path: Path) -> None:
    root = _book(tmp_path)
    with pytest.raises(Executed) as run:
        commands.cmd_exec(root, "local", ["env"], runner=FakeSaddlebag(), execute=_execute,
                          base={"HOME": "/h", "LOG_LEVEL": "info"})
    assert run.value.argv == ["saddlebag", "exec", "--env", "DATABASE_URL=db",
                              "--env", "STRIPE_KEY=stripe", "--", "env"]
    assert run.value.env == {"HOME": "/h", "API_URL": "http://localhost:8000",
                             "LOG_LEVEL": "debug", "FEATURE_FLAGS": "a,b"}


def test_exec_of_an_unknown_environment_fails_with_one_line(tmp_path: Path) -> None:
    outcome = commands.cmd_exec(_book(tmp_path), "staging", ["env"], runner=FakeSaddlebag(),
                                execute=_execute)
    assert not outcome.ok and "staging" in outcome.message


def test_exec_of_a_held_name_saddlebag_lacks_fails_before_running(tmp_path: Path) -> None:
    outcome = commands.cmd_exec(_book(tmp_path), "local", ["env"], runner=FakeSaddlebag([]),
                                execute=_execute)
    assert not outcome.ok and "DATABASE_URL" in outcome.message


def test_exec_with_no_command_prints_the_usage_and_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    args = argparse.Namespace(env_op="exec", environment="local", argv=["--"])
    assert env_cli.run(args, _book(tmp_path)) == 2
    assert "usage: ostler env exec" in capsys.readouterr().err


def test_dotenv_writes_the_file_and_ignores_it_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _book(tmp_path)
    first = commands.cmd_dotenv(root, "local")
    second = commands.cmd_dotenv(root, "local")
    assert first.ok and second.ok
    assert (root / ".env").read_text().splitlines()[-2:] == ["DATABASE_URL=", "STRIPE_KEY="]
    assert (root / ".gitignore").read_text() == ".env\n"
    assert first.message == f"wrote {root / '.env'} (5 variables, 2 held)\nadded .env to .gitignore"
    assert second.message == f"wrote {root / '.env'} (5 variables, 2 held)"


def test_dotenv_to_a_path_in_the_repo_ignores_that_path(tmp_path: Path) -> None:
    root = _book(tmp_path)
    assert commands.cmd_dotenv(root, "local", "config/.env.local").ok
    assert (root / "config" / ".env.local").is_file()
    assert (root / ".gitignore").read_text() == "config/.env.local\n"


def test_dotenv_to_a_path_outside_the_repo_leaves_gitignore_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _book(tmp_path / "repo")
    target = tmp_path / "elsewhere" / "stack.env"
    assert commands.cmd_dotenv(root, "local", str(target)).ok
    assert target.is_file() and not (root / ".gitignore").exists()
    assert "outside" in capsys.readouterr().err


def test_the_root_parser_keeps_env_as_the_command_and_the_rest_as_argv() -> None:
    from ostler.cli import _build_parser

    args = _build_parser().parse_args(["env", "exec", "local", "--", "env", "-0"])
    assert args.command == "env"
    assert args.env_op == "exec"
    assert args.argv == ["env", "-0"]
