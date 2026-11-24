"""Where a product keeps its milestones and design notes: under its folder in the artifacts folder, whatever the book's home."""

from __future__ import annotations

import pytest

from stablemate_core import books
from stablemate_core import config as cfgmod

from test_run_checkouts import _repo


@pytest.fixture
def world(tmp_path, monkeypatch, cfg_file):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    return {"artifacts": _repo(tmp_path / "artifacts"), "code": _repo(tmp_path / "acme-app")}


def test_a_repository_in_no_workspace_files_under_its_own_name(world):
    code, artifacts = world["code"], world["artifacts"]
    name = cfgmod.repository_name(code)

    assert books.product_home(code) == artifacts / "products" / name
    assert books.milestones_home(code) == artifacts / "products" / name / "milestones"
    assert books.designs_home(code) == artifacts / "products" / name / "designs"


def test_a_workspace_member_files_under_its_member_name(world, tmp_path, monkeypatch):
    code = world["code"]
    monkeypatch.setattr(cfgmod, "repository_name", lambda start: "member")

    assert books.milestones_home(code) == world["artifacts"] / "products" / "member" / "milestones"


def test_the_book_product_key_routes_to_that_product(world):
    code = world["code"]
    (code / "agents.yml").write_text("book:\n  product: acme\n")

    assert books.milestones_home(code) == world["artifacts"] / "products" / "acme" / "milestones"
    assert books.designs_home(code) == world["artifacts"] / "products" / "acme" / "designs"


def test_a_book_kept_in_the_repository_does_not_move_them(world):
    code = world["code"]
    (code / "agents.yml").write_text("book:\n  home: repo\n  product: acme\n")

    assert books.milestones_home(code) == world["artifacts"] / "products" / "acme" / "milestones"


def test_an_artifacts_folder_given_by_the_caller_wins(world, tmp_path):
    other = tmp_path / "other"

    assert books.product_home(world["code"], other) == other / "products" / cfgmod.repository_name(world["code"])


def test_a_start_inside_the_artifacts_folder_has_no_product(world):
    artifacts = world["artifacts"]

    assert books.product_home(artifacts) is None
    assert books.milestones_home(artifacts) is None
    assert books.designs_home(artifacts) is None
