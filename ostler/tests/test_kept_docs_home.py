"""Decisions and ADRs of every repository are kept in the artifacts folder, and its milestones under its product there, whether or not a workspace lists it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import git, milestones_root, repository, write, write_prefix
from ostler import Ostler, layout
from ostler._vendor.stablemate_core import config as core_config
from ostler.cli import main
from ostler.model import load


@pytest.fixture
def artifacts() -> Path:
    return Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()


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


DECISION = "---\nrepo: api-service\nstatus: accepted\nsummary: s\n---\n"
PAGE_NOTE = (
    "Each moved page needs `date:` and `status:` lines in place of its frontmatter, and a page that "
    "explains one element of one service moves to that service's `decisions/` folder."
)


def test_a_decision_in_the_artifacts_folder_is_refused_with_a_git_move_to_the_product(tmp_path, artifacts):
    repo = repository(tmp_path / "api-service")
    write(artifacts / "docs/decisions/x/decision.md", DECISION)

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    message = str(raised.value)
    assert f"mkdir -p {artifacts}/products/api-service" in message
    assert f"git -C {artifacts} mv docs/decisions/x/decision.md products/api-service/x.md" in message
    assert message.endswith(PAGE_NOTE)


def test_a_decision_in_a_code_repository_is_refused_with_a_plain_move_and_an_index_removal(tmp_path, artifacts):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/x/decision.md", DECISION)

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    message = str(raised.value)
    assert f"mkdir -p {artifacts}/products/api-service" in message
    assert f"mv {repo}/docs/decisions/x/decision.md {artifacts}/products/api-service/x.md" in message
    assert f"git -C {repo} rm -r --cached docs/decisions" in message
    assert message.endswith(PAGE_NOTE)


def test_a_taken_target_moves_to_the_next_free_numbered_name(tmp_path, artifacts):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/x/decision.md", DECISION)
    write(artifacts / "docs/decisions/x/decision.md", DECISION)
    write(artifacts / "products/api-service/x.md", "date: 2026-11-24\n\nTaken.\n")

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    message = str(raised.value)
    assert f"{artifacts}/products/api-service/x-2.md" in message
    assert f"git -C {artifacts} mv docs/decisions/x/decision.md products/api-service/x-3.md" in message


def test_the_printed_commands_clear_the_refusal(tmp_path, artifacts):
    repo = repository(tmp_path / "api-service")
    core_config.ensure_artifacts_repo()
    write(artifacts / "docs/decisions/x/decision.md", DECISION)
    git("-C", str(artifacts), "add", "docs")
    git("-C", str(artifacts), "-c", "core.hooksPath=/dev/null", "-c", "user.name=t",
        "-c", "user.email=t@example.com", "commit", "--quiet", "-m", "old")
    with pytest.raises(layout.LayoutMoveRequired) as raised:
        load(repo)

    for line in str(raised.value).splitlines()[1:-2]:
        subprocess.run(line.strip(), shell=True, check=True, timeout=30)

    load(repo)
    assert (artifacts / "products/api-service/x.md").is_file()


def test_a_decision_with_no_repo_key_is_not_refused(tmp_path):
    repo = repository(tmp_path / "api-service")
    write(repo / "docs/decisions/x/decision.md", "# notes\n")
    write(repo / "docs/decisions/notes.md", "# notes\n")

    load(repo)


def test_the_decisions_command_is_gone(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")

    with pytest.raises(SystemExit) as raised:
        main(["-C", str(repo), "decisions", "add", "x", "--summary", "s"])

    assert raised.value.code == 2
    assert not (Path(os.environ[core_config.ARTIFACTS_DIR_ENV]) / "docs").exists()


def _repository_with_old_folders_and_a_worktree(tmp_path) -> tuple[Path, Path]:
    main_checkout = repository(tmp_path / "api-service")
    write(main_checkout / "docs/decisions/x/decision.md", DECISION)
    write(main_checkout / "docs/milestones/0001-a/milestone.md", "---\ntype: milestone\ntitle: A\nstatus: proposed\n---\n")
    git("-C", str(main_checkout), "add", "docs")
    git("-C", str(main_checkout), "-c", "user.name=t", "-c", "user.email=t@example.com",
        "commit", "--quiet", "-m", "docs")
    linked = tmp_path / "linked"
    git("-C", str(main_checkout), "worktree", "add", "--quiet", str(linked))
    return main_checkout, linked


def test_a_linked_worktree_is_not_refused_once_the_main_checkout_has_moved_its_documents(tmp_path, artifacts):
    main_checkout, linked = _repository_with_old_folders_and_a_worktree(tmp_path)
    git("-C", str(main_checkout), "rm", "-r", "--quiet", "docs")
    git("-C", str(main_checkout), "-c", "user.name=t", "-c", "user.email=t@example.com",
        "commit", "--quiet", "-m", "moved")
    assert (linked / "docs/decisions/x/decision.md").is_file()

    layout.check(artifacts, linked)


def test_a_linked_worktree_is_judged_by_its_main_checkout_and_the_commands_name_it(tmp_path, artifacts):
    main_checkout, linked = _repository_with_old_folders_and_a_worktree(tmp_path)

    with pytest.raises(layout.LayoutMoveRequired) as raised:
        layout.check(artifacts, linked)

    message = str(raised.value)
    assert f"mv {main_checkout}/docs/decisions/x/decision.md {artifacts}/products/api-service/x.md" in message
    assert f"mv {main_checkout}/docs/milestones/0001-a" in message
    assert str(linked) not in message
