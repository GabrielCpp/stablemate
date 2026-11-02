"""`write_agents_yml` gives a new repo the id prefix its first mint needs, and keeps one already set."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from workhorse_workflows.coder.genesis.nodes import write_agents_yml

LOGGER = logging.getLogger("test.genesis")
SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,15}")


def _written(target: Path) -> dict:
    return YAML(typ="safe").load(target / "agents.yml")


def _target(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    target.mkdir()
    return target


def test_a_new_repo_gets_a_valid_id_prefix(tmp_path: Path) -> None:
    target = _target(tmp_path, "todo-app")

    write_agents_yml(LOGGER, target_dir=str(target))

    assert _written(target)["repo"]["id_prefix"] == "TODO"


def test_an_existing_id_prefix_is_kept(tmp_path: Path) -> None:
    target = _target(tmp_path, "todo-app")
    (target / "agents.yml").write_text("repo:\n  id_prefix: KEEP\n", encoding="utf-8")

    write_agents_yml(LOGGER, target_dir=str(target))

    assert _written(target)["repo"]["id_prefix"] == "KEEP"


@pytest.mark.parametrize(
    ("name", "prefix"),
    [("2fast-app", "FAST"), ("123", "REPO"), ("ai", "AI"), ("---", "REPO")],
)
def test_a_name_that_is_no_prefix_still_gives_a_valid_one(tmp_path: Path, name: str, prefix: str) -> None:
    target = _target(tmp_path, name)

    write_agents_yml(LOGGER, target_dir=str(target))

    written = _written(target)["repo"]["id_prefix"]
    assert written == prefix
    assert SHAPE.fullmatch(written)
