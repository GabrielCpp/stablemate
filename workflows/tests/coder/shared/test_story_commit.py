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
from workhorse_workflows.coder.shared.worktree import digest


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


def test_the_story_commit_leaves_the_artifacts_dir_and_tool_output_to_the_lanes_that_wrote_them(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(repo / "artifacts"))
    write(repo / "artifacts" / "specs" / "the-story" / "qa-okf-context.json", "{}\n")
    write(repo / "__screenshots__" / "failure.png", "png\n")
    write(repo / "feature.py", "VALUE = 1\n")

    result = story_commit.commit_story(
        logger, story_slug="the-story", repo_dir=str(repo), roots=[str(repo)]
    )

    assert result.committed
    landed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert landed == ["feature.py"], landed


def test_a_refused_story_commit_comes_back_as_the_refusal_and_stamps_nothing(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    hook = write(
        repo / ".git" / "hooks" / "pre-commit",
        f"#!{sys.executable}\nimport sys\nprint('feature.py repeats other.py', file=sys.stderr)\nsys.exit(1)\n",
    )
    hook.chmod(0o755)
    write(repo / "feature.py", "VALUE = 1\n")
    before = git(repo, "rev-parse", "HEAD").stdout

    result = story_commit.commit_story(
        logger, story_slug="the-story", repo_dir=str(repo), roots=[str(repo)]
    )

    assert not result.committed
    assert "feature.py repeats other.py" in result.refused, result
    assert git(repo, "rev-parse", "HEAD").stdout == before
    assert git(repo, "diff", "--cached", "--name-only").stdout == ""


EPIC = "EPIC-1"
SLUG = "STORY-1"
STORY_FOLDER = "stories/EPIC-1/STORY-1"
SPEC = "specs/STORY-1"

PLAN = """
from ostler_qa import Qa, scenario, target

app = target("app")


@scenario(target=app, mechanism="live", covers=["claim:1"], id="serves")
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
    write(repo / "services" / "app" / "service.py", "SERVICE = 1\n")
    write(repo / "src" / "server.py", "def run():\n    return 1\n")
    write(repo / STORY_FOLDER / "story.md", "# story\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    monkeypatch.chdir(repo)
    return str(spec)


def _scope(
    logger: logging.Logger,
    repo: Path,
    spec: str,
    dirty: list[str],
    proven: list[str] | None = None,
) -> ProofScope:
    return story_commit.proof_scope(
        logger,
        story_slug=SLUG,
        spec_dir=spec,
        story_path=f"{STORY_FOLDER}/story.md",
        dirty=dirty,
        repo_dir=str(repo),
        proven=proven,
    )


def _proven(repo: Path, dirty: list[str]) -> list[str]:
    prefix = f"{repo.name}:"
    return [f"{key}\0{digest(repo, key[len(prefix):])}" for key in dirty]


def test_leftovers_unchanged_since_qa_passed_reopen_nothing(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "src" / "server.py", "def run():\n    return 2\n")
    write(repo / "fixtures" / "seed.json", "{}\n")
    dirty = [f"{repo.name}:src/server.py", f"{repo.name}:fixtures/seed.json"]

    result = _scope(logger, repo, spec, dirty, _proven(repo, dirty))

    assert result.kind == "inert", result


def test_a_leftover_edited_after_qa_passed_reopens_the_proof(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "src" / "server.py", "def run():\n    return 2\n")
    write(repo / "fixtures" / "seed.json", "{}\n")
    dirty = [f"{repo.name}:src/server.py", f"{repo.name}:fixtures/seed.json"]
    proven = _proven(repo, dirty)
    write(repo / "src" / "server.py", "def run():\n    return 3\n")

    result = _scope(logger, repo, spec, dirty, proven)

    assert result.kind == "whole", result


def test_a_backlog_record_and_a_spec_file_in_an_artifacts_dir_inside_the_repo_are_inert(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(repo / "artifacts"))
    write(repo / "artifacts" / "backlogs" / "qa" / "record.json", "{}\n")
    write(repo / "artifacts" / "specs" / SLUG / "notes.json", "{}\n")
    dirty = [
        f"{repo.name}:artifacts/backlogs/qa/record.json",
        f"{repo.name}:artifacts/specs/{SLUG}/notes.json",
    ]

    result = _scope(logger, repo, spec, dirty)

    assert result.kind == "inert", result


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


def test_any_product_leftover_or_another_repos_path_reruns_the_whole_plan(
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


def test_the_book_delta_commit_lands_new_and_edited_book_files_and_leaves_the_rest(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "services" / "app" / "stale.py", "STALE = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "stale file")
    write(repo / "services" / "app" / "stale.py", "STALE = 2\n")
    snapshot = [f"services/app/stale.py\0{digest(repo, 'services/app/stale.py')}"]
    write(repo / "services" / "app" / "service.py", "SERVICE = 2\n")
    write(repo / "services" / "app" / "journeys" / "fresh.py", "JOURNEY = 1\n")
    write(repo / "src" / "server.py", "def run():\n    return 2\n")

    result = story_commit.commit_book_delta(
        logger,
        epic=EPIC,
        story_slug=SLUG,
        spec_dir=spec,
        preexisting=snapshot,
        repo_dir=str(repo),
        book_services=["app"],
    )

    assert result.committed
    landed = git(repo, "show", "--name-only", "--format=%s", "HEAD").stdout.split("\n")
    assert landed[0].startswith("docs(acme): specify STORY-1 in the book"), landed
    assert sorted(line for line in landed[1:] if line) == [
        "services/app/journeys/fresh.py",
        "services/app/service.py",
    ]
    assert sorted(git(repo, "status", "--porcelain").stdout.splitlines()) == [
        " M services/app/stale.py",
        " M src/server.py",
    ]


def test_the_clean_check_skips_the_artifacts_dir_only_when_asked(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(repo / "artifacts"))
    write(repo / "artifacts" / "backlogs" / "qa" / "record.json", "{}\n")
    write(repo / "src" / "extra.py", "X = 1\n")

    kept = story_commit.check_repos_clean(
        logger, story_slug=SLUG, spec_dir=spec, repo_dir=str(repo), skip_artifacts=True
    )
    counted = story_commit.check_repos_clean(
        logger, story_slug=SLUG, spec_dir=spec, repo_dir=str(repo)
    )

    assert kept.dirty == [f"{repo.name}:src/extra.py"], kept
    assert sorted(counted.dirty) == [
        f"{repo.name}:artifacts/backlogs/qa/record.json",
        f"{repo.name}:src/extra.py",
    ], counted


def test_the_book_delta_commit_has_nothing_to_land_when_the_book_is_clean(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "src" / "server.py", "def run():\n    return 2\n")

    result = story_commit.commit_book_delta(
        logger, epic=EPIC, story_slug=SLUG, spec_dir=spec, repo_dir=str(repo)
    )

    assert not result.committed
    assert git(repo, "status", "--porcelain").stdout.strip() == "M src/server.py"


def test_a_covered_services_spec_delta_commit_holds_only_its_book_folder(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spec = _book(repo, write, git, monkeypatch, tmp_path)
    write(repo / "services" / "api" / "service.py", "SERVICE = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the api book")
    write(repo / "services" / "api" / "journeys" / "publish.py", "JOURNEY = 1\n")
    write(repo / "services" / "api" / "service.py", "SERVICE = 2\n")
    write(repo / "docs" / "notes" / "fresh.md", "# fresh\n")
    write(repo / "src" / "server.py", "def run():\n    return 2\n")

    result = story_commit.commit_book_delta(
        logger,
        epic=EPIC,
        story_slug=SLUG,
        spec_dir=spec,
        repo_dir=str(repo),
        book_services=["api"],
    )

    assert result.committed
    landed = git(repo, "show", "--name-only", "--format=%s", "HEAD").stdout.split("\n")
    assert sorted(line for line in landed[1:] if line) == [
        "services/api/journeys/publish.py",
        "services/api/service.py",
    ]
    assert sorted(git(repo, "status", "--porcelain").stdout.splitlines()) == [
        " M src/server.py",
        "?? docs/",
    ]
