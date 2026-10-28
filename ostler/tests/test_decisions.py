"""``ostler decisions add`` files an empty decision at ``<docs home>/docs/decisions/<slug>/decision.md``."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import write
from ostler import decisions, index, textindex
from ostler._vendor.stablemate_core import config as core_config
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load


def git(*argv: str) -> None:
    subprocess.run(["git", *argv], check=True, capture_output=True, timeout=30)


def repository(path: Path) -> Path:
    git("init", "--quiet", str(path))
    write(path / "README.md", "# repo\n")
    git("-C", str(path), "add", "README.md")
    git("-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com",
        "commit", "--quiet", "-m", "init")
    return path


def workspace_of(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *members: Path) -> None:
    listed = ", ".join(f'"{m}"' for m in members)
    config = tmp_path / "home.toml"
    config.write_text(f"[workspaces]\nacme = [{listed}]\n")
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))


def artifacts() -> Path:
    return Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()


def frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---\n")[1])


def test_add_writes_the_shape_and_prints_the_path(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")

    code = main(["-C", str(repo), "decisions", "add", "shared-libs-live-in-libs",
                 "--repo", "api-service", "--summary", "Shared code lives under libs/<name>"])

    target = repo / "docs/decisions/shared-libs-live-in-libs/decision.md"
    assert code == 0
    assert capsys.readouterr().out.strip() == str(target)
    assert frontmatter(target) == {
        "repo": "api-service", "status": "accepted", "summary": "Shared code lives under libs/<name>",
    }
    headings = [line for line in target.read_text().splitlines() if line.startswith("## ")]
    assert headings == ["## Question", "## Decided", "## Grounded in", "## Context"]


def test_a_taken_slug_is_refused_and_leaves_the_file_alone(tmp_path, capsys):
    repo = repository(tmp_path / "api-service")
    main(["-C", str(repo), "decisions", "add", "taken", "--summary", "first"])
    target = repo / "docs/decisions/taken/decision.md"
    capsys.readouterr()

    code = main(["-C", str(repo), "decisions", "add", "taken", "--summary", "second"])

    assert code == 1
    assert "already exists" in capsys.readouterr().out
    assert frontmatter(target)["summary"] == "first"


@pytest.mark.parametrize("slug", ["Shared Libs", "a_b", "a-", "a--b", "x" * 61, ""])
def test_a_slug_that_is_not_short_kebab_case_is_refused(tmp_path, slug):
    repo = repository(tmp_path / "api-service")

    assert main(["-C", str(repo), "decisions", "add", slug, "--summary", "s"]) == 1
    assert not (repo / "docs/decisions").exists()


def test_an_empty_summary_is_refused(tmp_path):
    repo = repository(tmp_path / "api-service")

    assert main(["-C", str(repo), "decisions", "add", "ok", "--summary", "  "]) == 1


def test_repo_defaults_to_the_normalised_basename_outside_any_workspace(tmp_path):
    repo = repository(tmp_path / "Web_App")

    main(["-C", str(repo), "decisions", "add", "ok", "--summary", "s"])

    assert frontmatter(repo / "docs/decisions/ok/decision.md")["repo"] == "web-app"


def test_a_member_files_under_the_artifacts_dir_with_its_configured_name(tmp_path, monkeypatch):
    repo = repository(tmp_path / "code" / "api-service")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = [{{ path = "{repo}", name = "billing-api" }}]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))

    main(["-C", str(repo), "decisions", "add", "ok", "--summary", "s"])

    assert frontmatter(artifacts() / "docs/decisions/ok/decision.md")["repo"] == "billing-api"
    assert not (repo / "docs").exists()


def test_a_worktree_of_a_member_files_in_the_same_folder_under_the_member_name(tmp_path, monkeypatch):
    repo = repository(tmp_path / "code" / "api-service")
    workspace_of(tmp_path, monkeypatch, repo)
    tree = tmp_path / "trees" / "story-1"
    git("-C", str(repo), "worktree", "add", "--quiet", "-b", "story-1", str(tree))

    main(["-C", str(tree), "decisions", "add", "ok", "--summary", "s"])

    assert frontmatter(artifacts() / "docs/decisions/ok/decision.md")["repo"] == "api-service"
    assert decisions.add(load(repo), "ok", repo="api-service", summary="s").ok is False


def test_the_facade_files_the_same_decision(tmp_path):
    repo = repository(tmp_path / "api-service")

    result = Ostler(repo).decision_add("ok", summary="s")

    assert result.ok
    assert result.paths == [repo / "docs/decisions/ok/decision.md"]
    assert frontmatter(result.paths[0])["repo"] == "api-service"


def test_search_finds_a_decision_by_a_word_in_its_slug(tmp_path):
    repo = repository(tmp_path / "api-service")
    main(["-C", str(repo), "decisions", "add", "shared-libs-live-in-libs", "--summary", "Where shared code goes"])
    graph = load(repo)

    with index.session(repo, directory=str(tmp_path / "idx"), enabled=True):
        found = textindex.search(graph, "libs", root="decisions")

    assert [hit["path"] for hit in found] == ["docs/decisions/shared-libs-live-in-libs/decision.md"]
