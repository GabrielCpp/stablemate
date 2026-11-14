"""`ostler env exec` against a book whose stack root names its secrets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from ostler.environments import cli as env_cli



def _book(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def test_exec_with_no_command_prints_the_usage_and_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    args = argparse.Namespace(env_op="exec", copy="", argv=["--"])
    assert env_cli.run(args, _book(tmp_path)) == 2
    assert "usage: ostler env exec" in capsys.readouterr().err


def test_the_root_parser_keeps_env_as_the_command_and_the_rest_as_argv() -> None:
    from ostler.cli import _build_parser

    args = _build_parser().parse_args(["env", "exec", "--copy", "story-1", "--", "env", "-0"])
    assert args.command == "env"
    assert args.env_op == "exec"
    assert args.copy == "story-1"
    assert args.argv == ["--", "env", "-0"]
