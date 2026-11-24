"""Decisions and ADRs of every repository are kept in the artifacts folder, and its milestones under its product there, whether or not a workspace lists it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import milestones_root, repository, write, write_prefix
from ostler import Ostler, adr, index, layout, register, textindex
from ostler._vendor.stablemate_core import config as core_config
from ostler.cli import main
from ostler.model import load


@pytest.fixture
def artifacts_docs() -> Path:
    return Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve() / "docs"


def test_a_decision_of_a_repository_in_no_workspace_is_filed_in_the_artifacts_folder(
    tmp_path, capsys, artifacts_docs,
):
    repo = repository(tmp_path / "api-service")

    code = main(["-C", str(repo), "decisions", "add", "use-x", "--repo", "api-service", "--summary", "X"])

    assert code == 0
    assert capsys.readouterr().out.strip() == str(artifacts_docs / "decisions/use-x/decision.md")
    assert (artifacts_docs / "decisions/use-x/decision.md").is_file()
    assert not (repo / "docs").exists()


def test_a_milestone_is_filed_under_its_product_in_the_artifacts_folder_and_queried(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")
    write_prefix(repo)
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()

    assert main(["-C", str(repo), "create", "milestone", "ms", "--title", "Ms"]) == 0
    capsys.readouterr()

    assert (artifacts / "products/api-service/milestones/0001-ms/milestone.md").is_file()
    assert not (repo / "docs").exists()
    assert main(["-C", str(repo), "list", "--type", "milestone"]) == 0
    assert "ms" in capsys.readouterr().out


def test_a_second_repository_numbers_its_milestones_from_one(tmp_path):
    first = repository(tmp_path / "api-service")
    second = repository(tmp_path / "web-app")
    write_prefix(first)
    write_prefix(second)

    assert main(["-C", str(first), "create", "milestone", "one", "--title", "One"]) == 0
    assert main(["-C", str(first), "create", "milestone", "two", "--title", "Two"]) == 0
    assert main(["-C", str(second), "create", "milestone", "ms", "--title", "Ms"]) == 0

    assert (milestones_root(first) / "0002-two/milestone.md").is_file()
    assert (milestones_root(second) / "0001-ms/milestone.md").is_file()


def test_the_book_product_key_routes_milestones_to_that_product(tmp_path):
    repo = repository(tmp_path / "api-service")
    write(repo / "agents.yml", "repo:\n  id_prefix: X\nbook:\n  product: acme\n")
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()

    assert main(["-C", str(repo), "create", "milestone", "ms", "--title", "Ms"]) == 0

    assert (artifacts / "products/acme/milestones/0001-ms/milestone.md").is_file()


def test_a_milestone_is_refused_from_the_artifacts_folder(tmp_path, capsys):
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    write_prefix(artifacts)

    assert main(["-C", str(artifacts), "create", "milestone", "ms", "--title", "Ms"]) == 1

    assert "run from the code repository the milestone is for (`ostler -C <repo>`)" in capsys.readouterr().out
    assert not (artifacts / "products").exists()


def test_a_repository_still_holding_a_milestone_is_refused_with_the_move(tmp_path):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/milestones/0001-x/milestone.md", "---\ntype: milestone\ntitle: X\nstatus: proposed\n---\n")
    target = milestones_root(repo)

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    message = str(raised.value)
    assert f"mkdir -p {target}" in message
    assert f"mv {repo}/docs/milestones/0001-x {target}/0001-x" in message
    assert f"git -C {repo} rm -r --cached docs/milestones" in message


def test_a_taken_milestone_number_moves_to_the_next_free_one(tmp_path):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/milestones/0001-x/milestone.md", "---\ntype: milestone\ntitle: X\nstatus: proposed\n---\n")
    write(milestones_root(repo) / "0001-y/milestone.md", "---\ntype: milestone\ntitle: Y\nstatus: proposed\n---\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    assert f"{milestones_root(repo)}/0002-x" in str(raised.value)


def test_milestones_left_in_the_artifacts_folder_are_refused_with_a_git_move(tmp_path):
    repo = repository(tmp_path / "api-service")
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    write(artifacts / "docs/milestones/0001-x/milestone.md", "---\ntype: milestone\ntitle: X\nstatus: proposed\n---\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    assert f"git -C {artifacts} mv docs/milestones/0001-x products/api-service/milestones/0001-x" in str(raised.value)


def test_product_pages_list_only_the_flat_pages_beside_the_milestones_and_designs(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")
    write(repo / "agents.yml", "repo:\n  id_prefix: X\n")
    product = milestones_root(repo).parent
    write(product / "overview.md", "date: 2026-11-21\n\nThe product is a shop.\n")
    assert main(["-C", str(repo), "create", "milestone", "ms", "--title", "Ms"]) == 0
    write(product / "designs/sketch.md", "date: 2026-11-21\n\nA sketch of the shop.\n")
    capsys.readouterr()

    assert main(["-C", str(repo), "book", "pages", "--level", "product"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if "overview" in line]
    assert not [line for line in lines if "sketch" in line or "milestone" in line]
    assert (product / "milestones").is_dir() and (product / "designs").is_dir()


def test_a_member_milestone_is_found_from_the_member_checkout(tmp_path, monkeypatch):
    member = repository(tmp_path / "code" / "api-service")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{member}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()
    write_prefix(artifacts)
    write(milestones_root(member) / "0001-ms/milestone.md",
          "---\ntype: milestone\ntitle: Ms\nstatus: approved\n---\n# Ms\n")

    assert Ostler(artifacts, start=member).approved_milestone().name == "0001-ms"
    assert Ostler(artifacts).graph.milestones == []


def test_repositories_sharing_the_folder_see_each_others_decisions_and_never_reuse_a_slug(tmp_path):
    first = repository(tmp_path / "api-service")
    second = repository(tmp_path / "web-app")
    assert main(["-C", str(first), "decisions", "add", "first-one", "--summary", "A"]) == 0
    assert main(["-C", str(second), "decisions", "add", "second-one", "--summary", "B"]) == 0

    with index.session(second, directory=str(tmp_path / "idx"), enabled=True):
        found = textindex.search(load(second), "one", root="decisions")

    assert sorted(Path(hit["path"]).parent.name for hit in found) == ["first-one", "second-one"]
    assert main(["-C", str(second), "decisions", "add", "first-one", "--summary", "C"]) == 1


def test_a_proposed_adr_is_committed_when_the_artifacts_folder_is_a_repository(tmp_path, artifacts_docs):
    core_config.ensure_artifacts_repo()
    home = repository(tmp_path / "api-service")
    graph = load(home)
    filing = register.file_record(
        graph, repo="api-service", area="cart", pattern="guard-the-total", summary="s",
        filed_by="qa", record_id="acme-1", body="b",
    )
    assert filing.ok, filing.message

    result = adr.propose(
        load(home), slug="guard-every-total", title="Guard every total", context="c",
        decision="d", consequences="q", evidence=["acme-1"],
    )

    assert result.ok, result.message
    tracked = subprocess.run(
        ["git", "-C", str(artifacts_docs.parent), "ls-files", "docs/adrs"],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.split()
    assert tracked == ["docs/adrs/guard-every-total/adr.md"]


def test_a_repository_still_holding_a_decision_is_refused_with_the_move(tmp_path, artifacts_docs):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/x/decision.md", "---\nrepo: api-service\nsummary: s\n---\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    assert f"mv {repo}/docs/decisions/x {artifacts_docs}/decisions/x" in str(raised.value)
    assert "git -C" in str(raised.value)


def test_a_taken_slug_moves_to_a_name_with_the_repository(tmp_path, artifacts_docs):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/x/decision.md", "---\nrepo: api-service\nsummary: s\n---\n")
    write(artifacts_docs / "decisions/x/decision.md", "---\nrepo: web-app\nsummary: s\n---\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    assert f"{artifacts_docs}/decisions/x-api-service" in str(raised.value)


def test_a_file_with_no_ostler_shape_is_not_refused(tmp_path):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/notes.md", "# notes\n")

    load(repo)
