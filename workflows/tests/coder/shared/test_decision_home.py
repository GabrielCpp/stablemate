"""A coder run and an interactive session on one member repository file and read decisions in one folder."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from ostler import textindex
from ostler._vendor.stablemate_core import config as core_config
from ostler.cli import main
from ostler.model import load
from workhorse_workflows.coder.shared import resolution


def git(*argv: str) -> None:
    subprocess.run(["git", *argv], check=True, capture_output=True, timeout=30)


@pytest.fixture
def member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "code" / "api-service"
    repo.mkdir(parents=True)
    git("init", "--quiet", str(repo))
    (repo / "README.md").write_text("# api\n")
    git("-C", str(repo), "add", "README.md")
    git("-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
        "commit", "--quiet", "-m", "init")
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{repo}"]\n')
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    return repo


def test_a_run_and_a_session_resolve_the_same_decisions_folder(member, tmp_path, capsys):
    tree = tmp_path / "trees" / "story-1"
    git("-C", str(member), "worktree", "add", "--quiet", "-b", "story-1", str(tree))
    artifacts = Path(os.environ[core_config.ARTIFACTS_DIR_ENV]).resolve()

    from_member = resolution.decisions_dir(str(member))
    from_tree = resolution.decisions_dir(str(tree))

    assert from_member == from_tree == artifacts / "docs" / "decisions"

    assert main(["-C", str(tree), "decisions", "add", "shared-libs-live-in-libs",
                 "--summary", "Where shared code lives"]) == 0
    filed = Path(capsys.readouterr().out.strip())

    assert filed == from_member / "shared-libs-live-in-libs" / "decision.md"
    assert main(["-C", str(member), "decisions", "add", "shared-libs-live-in-libs",
                 "--summary", "Again"]) == 1


def test_search_returns_a_decision_filed_by_either_agent(member, tmp_path, capsys):
    tree = tmp_path / "trees" / "story-1"
    git("-C", str(member), "worktree", "add", "--quiet", "-b", "story-1", str(tree))
    main(["-C", str(member), "decisions", "add", "billing-currency-rounding", "--summary", "Round half up"])
    main(["-C", str(tree), "decisions", "add", "billing-invoice-numbering", "--summary", "Numbers never reuse"])
    capsys.readouterr()

    found = textindex.search(load(member), "billing", root="decisions")

    assert sorted(hit["path"] for hit in found) == [
        "docs/decisions/billing-currency-rounding/decision.md",
        "docs/decisions/billing-invoice-numbering/decision.md",
    ]
