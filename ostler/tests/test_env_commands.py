"""`ostler env exec` and `ostler env dotenv` against a book with an environment page."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import pytest

from ostler.environments import cli as env_cli



class Executed(Exception):
    def __init__(self, argv: list[str], env: Mapping[str, str]) -> None:
        super().__init__(argv)
        self.argv = argv
        self.env = env


def _execute(argv: list[str], env: Mapping[str, str]) -> NoReturn:
    raise Executed(argv, env)


def _book(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def test_exec_with_no_command_prints_the_usage_and_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    args = argparse.Namespace(env_op="exec", environment="local", argv=["--"])
    assert env_cli.run(args, _book(tmp_path)) == 2
    assert "usage: ostler env exec" in capsys.readouterr().err


def test_the_root_parser_keeps_env_as_the_command_and_the_rest_as_argv() -> None:
    from ostler.cli import _build_parser

    args = _build_parser().parse_args(["env", "exec", "local", "--", "env", "-0"])
    assert args.command == "env"
    assert args.env_op == "exec"
    assert args.argv == ["env", "-0"]
