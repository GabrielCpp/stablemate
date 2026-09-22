"""The strict scope in pyproject.toml, and the checkers that must agree with it."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import strict_scope

REPO = Path(__file__).resolve().parents[2]
SHAPE_RULES = ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "ANN401"]


def _setting(*keys: str) -> object:
    with (REPO / "pyproject.toml").open("rb") as handle:
        table: object = tomllib.load(handle)
    for key in ("tool", *keys):
        assert isinstance(table, dict)
        table = table.get(key)
    return table


def _scope_paths() -> list[str]:
    return list(strict_scope.load(REPO).paths)


def test_basedpyright_is_strict_over_exactly_the_scope() -> None:
    assert _setting("basedpyright", "strict") == _scope_paths()


def test_basedpyright_bans_any_over_exactly_the_scope() -> None:
    environments = _setting("basedpyright", "executionEnvironments")
    assert isinstance(environments, list)
    banned = [
        env.get("root")
        for env in environments
        if isinstance(env, dict)
        and env.get("reportAny") == "error"
        and env.get("reportExplicitAny") == "error"
    ]
    assert banned == _scope_paths()


def test_ruff_exempts_everything_outside_the_scope_from_the_shape_rules() -> None:
    outside = "!{" + ",".join(f"{path}/**" for path in _scope_paths()) + "}"
    assert _setting("ruff", "lint", "per-file-ignores", outside) == SHAPE_RULES
    selected = _setting("ruff", "lint", "extend-select")
    assert isinstance(selected, list)
    assert set(SHAPE_RULES) <= set(selected)


PLANTED = """\
from typing import Any


def planted(a: Any, b: int, c: int, d: int, e: int, f: int) -> int:
    return b
"""


def _ruff_codes(filename: str) -> set[str]:
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "concise", "--stdin-filename", filename, "-"],
        input=PLANTED,
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    return {code for code in SHAPE_RULES if f" {code} " in completed.stdout}


@pytest.mark.parametrize("root", _scope_paths())
def test_ruff_flags_a_planted_function_inside_the_scope(root: str) -> None:
    assert _ruff_codes(f"{root}/planted.py") == {"PLR0913", "ANN401"}


def test_ruff_leaves_the_same_function_alone_outside_the_scope() -> None:
    assert _ruff_codes("workflows/src/workhorse_workflows/planted.py") == set()


@pytest.mark.parametrize(
    "body",
    [
        "[tool.other]\nx = 1\n",
        '[tool.stablemate.strict]\npaths = "pkg/strict"\nmax-lines = 400\n',
        '[tool.stablemate.strict]\npaths = ["pkg/strict", 3]\nmax-lines = 400\n',
        '[tool.stablemate.strict]\npaths = ["pkg/strict"]\nmax-lines = "400"\n',
    ],
)
def test_a_malformed_scope_is_refused_where_it_is_read(tmp_path: Path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(body, encoding="utf-8")
    with pytest.raises(strict_scope.ScopeError):
        strict_scope.load(tmp_path)
