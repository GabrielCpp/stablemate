"""The minted story id as the trailer identity — `prepare_story` and `changed_files`."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler, crud
from ostler.model import load
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows import coder
from workhorse_workflows.coder.shared.provenance import changed_files, resolve_story_sources
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry
from workhorse_workflows.coder.shared.story import prepare_story

LOGGER = logging.getLogger("test")


def _minted_book(tmp_path: Path) -> tuple[Ostler, str]:
    """A crud-built book with one story, returning its minted id."""
    crud.create_epic(load(tmp_path), "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "01-foo", "Foo")
    graph = load(tmp_path)
    found = graph.story_by_slug("01-foo")
    assert found is not None
    story_md = tmp_path / found[1].path
    body = story_md.read_text(encoding="utf-8")
    for heading, text in (
        ("Context", "Users need a thing."),
        ("Acceptance Criteria", "- the thing exists"),
        ("Non-Functional Acceptance Criteria", "- the thing is fast"),
        ("Technical Notes", "- the thing is a function"),
    ):
        body = body.replace(f"## {heading}\n\n", f"## {heading}\n\n{text}\n\n", 1)
    story_md.write_text(body, encoding="utf-8")
    return Ostler(tmp_path), found[1].eid


def test_prepare_story_resolves_a_slug_to_the_minted_id(tmp_path: Path) -> None:
    _, eid = _minted_book(tmp_path)
    paths = prepare_story(LOGGER, "01-foo", repo_dir=str(tmp_path))
    assert paths.story_id == eid
    assert paths.story_slug == "01-foo"


def test_prepare_story_takes_the_id_itself(tmp_path: Path) -> None:
    _, eid = _minted_book(tmp_path)
    paths = prepare_story(LOGGER, eid, repo_dir=str(tmp_path))
    assert paths.story_id == eid
    assert paths.story_slug == "01-foo"


def test_prepare_story_refuses_a_handle_the_graph_does_not_know(tmp_path: Path) -> None:
    _minted_book(tmp_path)
    with pytest.raises(WorkflowFailed):
        prepare_story(LOGGER, "no-such-story", repo_dir=str(tmp_path))


def test_changed_files_reads_commits_under_either_spelling(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> None:
    """One log walk answers to the id-trailer commit and the legacy slug-trailer one."""
    repo = tmp_path / "svc"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    for name, trailer in (("old.py", "01-foo"), ("new.py", "x-01ABCDEF")):
        (repo / name).write_text("pass\n", encoding="utf-8")
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", f"feat: add {name}\n\nStory: {trailer}")

    result = changed_files(LOGGER, str(repo), "01-foo", "x-01ABCDEF")
    assert {"old.py", "new.py"} <= set(result.paths)


def test_changed_files_without_an_id_still_greps_the_slug(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> None:
    repo = tmp_path / "svc"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "old.py").write_text("pass\n", encoding="utf-8")
    git(repo, "add", "old.py")
    git(repo, "commit", "-q", "-m", "feat: add old\n\nStory: 01-foo")

    assert "old.py" in changed_files(LOGGER, str(repo), "01-foo").paths


def test_story_sources_begin_before_the_earliest_exact_story_trailer(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> None:
    docs = tmp_path / "docs"
    repo = tmp_path / "api-service"
    docs.mkdir()
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "service.py").write_text("value = 0\n", encoding="utf-8")
    git(repo, "add", "service.py")
    git(repo, "commit", "-qm", "seed")
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    for value, trailer in ((1, "01-foo"), (2, "x-01ABCDEF")):
        (repo / "service.py").write_text(f"value = {value}\n", encoding="utf-8")
        git(repo, "add", "service.py")
        git(repo, "commit", "-q", "-m", f"feat: value {value}\n\nStory: {trailer}")

    result = resolve_story_sources(
        LOGGER,
        (
            DispatchEntry(
                service="api-service::src",
                repo="api-service",
                cwd=str(repo),
                service_path="src",
            ),
            DispatchEntry(
                service="api-service::worker",
                repo="api-service",
                cwd=str(repo),
                service_path="worker",
            ),
        ),
        "01-foo",
        "x-01ABCDEF",
        str(docs),
    )

    assert result.status == "valid"
    assert [source.root for source in result.sources] == ["src", "worker"]
    assert {source.base for source in result.sources} == {base}


def test_story_sources_reject_a_similar_but_nonexact_trailer(
    tmp_path: Path, git: Callable[..., subprocess.CompletedProcess]
) -> None:
    docs = tmp_path / "docs"
    repo = tmp_path / "api-service"
    docs.mkdir()
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "service.py").write_text("value = 1\n", encoding="utf-8")
    git(repo, "add", "service.py")
    git(repo, "commit", "-q", "-m", "seed\n\nStory: x-01ABCDEF-extra")

    result = resolve_story_sources(
        LOGGER,
        (
            DispatchEntry(
                service="api-service::.",
                repo="api-service",
                cwd=str(repo),
            ),
        ),
        "01-foo",
        "x-01ABCDEF",
        str(docs),
    )

    assert result.status == "invalid"
    assert "no commit carries an exact Story trailer" in result.errors[0]


def test_the_dev_prompt_commits_with_the_minted_story_identity() -> None:
    prompt = (
        Path(coder.__file__).parent / "dev/prompts/dev-review.md"
    ).read_text(encoding="utf-8")

    assert "`Story: {{ workhorse_var('story_id') }}`" in prompt
    assert "`Story: {{ workhorse_var('story_slug') }}`" not in prompt


def test_no_commit_prompt_brackets_the_story_id_into_the_subject() -> None:
    """The id has exactly one spelling — the `Story:` footer — and this is the guard."""
    prompts = Path(coder.__file__).parent
    offenders = [
        str(path.relative_to(prompts))
        for path in prompts.rglob("*.md")
        for text in (path.read_text(encoding="utf-8"),)
        if "[{{ workhorse_var('story_id') }}]" in text or "[{{ story_id }}]" in text
    ]

    assert offenders == []
