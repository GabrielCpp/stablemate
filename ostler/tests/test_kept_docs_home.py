"""Decisions, ADRs and milestones of every repository are kept in the artifacts folder, whether or not a workspace lists it."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import repository, write, write_prefix
from ostler import adr, index, layout, register, textindex
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


def test_a_milestone_stays_in_the_repository_and_is_queried(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")
    write_prefix(repo)

    assert main(["-C", str(repo), "create", "milestone", "ms", "--title", "Ms"]) == 0
    capsys.readouterr()

    assert [p.parent.name.endswith("-ms") for p in (repo / "docs/milestones").glob("*/milestone.md")] == [True]
    assert main(["-C", str(repo), "list", "--type", "milestone"]) == 0


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
