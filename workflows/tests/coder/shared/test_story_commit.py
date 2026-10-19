"""The story commit renders the repo's agent files first, so a skill the library changed since the last render does not refuse it."""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared import story_commit
from workhorse_workflows.coder.shared.schemas.queue import ProofScope


def test_the_agent_files_are_rendered_before_the_story_commit_so_their_drift_is_not_refused(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drift = write(repo / ".drifted", "stale skill\n")
    hook = write(
        repo / ".git" / "hooks" / "pre-commit",
        f"#!{sys.executable}\nimport pathlib, sys\nsys.exit(1 if pathlib.Path({str(drift)!r}).exists() else 0)\n",
    )
    hook.chmod(0o755)
    write(repo / "feature.py", "VALUE = 1\n")

    def _render(root: Path) -> str:
        (root / ".drifted").unlink(missing_ok=True)
        return ""

    monkeypatch.setattr(story_commit, "render_agent_files_returning_failure", _render)

    result = story_commit.commit_story(
        logger,
        story_slug="the-story",
        repo_dir=str(repo),
        roots=[str(repo)],
    )

    assert result.committed
    assert "the-story" in git(repo, "log", "-1", "--format=%s").stdout


EPIC = "EPIC-1"
SLUG = "STORY-1"
STORY_FOLDER = "docs/epics/EPIC-1/stories/STORY-1"
SPEC = "specs/STORY-1"

SERVER_PAGE = """---
type: cli
slug: server
title: the server
---
# the server

Serves things.

- binary: server
- code: src/server.py::run
"""

PLAN = """
from ostler_qa import Qa, scenario, target

app = target("app")


@scenario(target=app, mechanism="live", covers=["okf:docs/features/app/server.md:contract"], id="serves")
def serves(qa: Qa) -> None:
    qa.check("it serves", True)
"""


def _book(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> str:
    """A one-repo book with a cited file, a story folder and a plan, all committed; returns the spec dir."""
    spec = tmp_path / "artifacts" / SPEC
    write(spec / "qa_plan.py", PLAN)
    write(repo / "docs" / "features" / "app" / "server.md", SERVER_PAGE)
    write(repo / "src" / "server.py", "def run():\n    return 1\n")
    write(repo / STORY_FOLDER / "story.md", "# story\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    monkeypatch.chdir(repo)
    return str(spec)


def _scope(
    logger: logging.Logger, repo: Path, spec: str, dirty: list[str]
) -> ProofScope:
    return story_commit.proof_scope(
        logger,
        story_slug=SLUG,
        spec_dir=spec,
        story_path=f"{STORY_FOLDER}/story.md",
        dirty=dirty,
        docs_path=str(repo),
        repo_dir=str(repo),
    )


def test_a_story_markdown_leftover_is_inert(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)

    result = _scope(logger, repo, spec, [f"{repo.name}:{STORY_FOLDER}/story.md"])

    assert result.kind == "inert"


def test_a_cited_product_file_reruns_the_scenarios_covering_its_page(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)

    result = _scope(logger, repo, spec, [f"{repo.name}:src/server.py"])

    assert (result.kind, result.scenarios) == ("claims", ["serves"]), result


def test_an_edited_book_page_reruns_its_scenarios(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)

    result = _scope(logger, repo, spec, [f"{repo.name}:docs/features/app/server.md"])

    assert (result.kind, result.scenarios) == ("claims", ["serves"]), result


def test_an_uncited_file_or_another_repos_path_reruns_the_whole_plan(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)

    fixture = _scope(logger, repo, spec, [f"{repo.name}:fixtures/seed.json"])
    foreign = _scope(logger, repo, spec, ["web-app:src/page.ts"])

    assert fixture.kind == "whole", fixture
    assert foreign.kind == "whole", foreign


def test_the_leftovers_commit_lands_exactly_the_dirty_paths(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "src" / "server.py", "def run():\n    return 2\n")
    write(repo / "src" / "mine.py", "# not the run's\n")

    result = story_commit.commit_leftovers(
        logger,
        epic=EPIC,
        story_slug=SLUG,
        spec_dir=spec,
        dirty=[f"{repo.name}:src/server.py"],
        repo_dir=str(repo),
    )

    assert result.committed
    assert git(repo, "show", "--name-only", "--format=%s", "HEAD").stdout.split() [-1] == "src/server.py"
    assert git(repo, "status", "--porcelain").stdout.strip() == "?? src/mine.py"


def test_the_leftovers_commit_has_nothing_to_land_when_nothing_is_dirty(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)

    result = story_commit.commit_leftovers(
        logger, epic=EPIC, story_slug=SLUG, spec_dir=spec, dirty=[], repo_dir=str(repo)
    )

    assert not result.committed
