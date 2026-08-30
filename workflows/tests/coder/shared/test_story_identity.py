"""The minted story id as the trailer identity — `_story_id` and `changed_files`.

Commit trailers carry the story's minted frontmatter id (`ACME-01H…`) because it
survives a slug rename; the slug is the fallback for a book that predates minted ids.
What is worth testing is each end of that seam: the resolver that lifts the id off the
graph, and the read side that must keep answering to commits written under either
spelling.
"""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from ostler import Ostler, crud
from ostler.model import load

from workhorse_workflows import coder
from workhorse_workflows.coder.shared.dev import changed_files, resolve_story_sources
from workhorse_workflows.coder.shared.schemas.dev import DispatchEntry
from workhorse_workflows.coder.shared.story import _story_id

LOGGER = logging.getLogger("test")


def _minted_book(tmp_path: Path) -> tuple[Ostler, str]:
    """A crud-built book with one story, returning its minted id."""
    crud.create_epic(load(tmp_path), "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "01-foo", "Foo")
    graph = load(tmp_path)
    found = graph.find_story("01-foo")
    assert found is not None
    return Ostler(tmp_path), found[1].eid


def test_story_id_resolves_the_minted_id(tmp_path: Path) -> None:
    okf, eid = _minted_book(tmp_path)
    assert eid
    assert _story_id(okf, "01-foo") == eid


def test_story_id_is_empty_for_a_story_the_graph_does_not_know(tmp_path: Path) -> None:
    okf, _ = _minted_book(tmp_path)
    assert _story_id(okf, "no-such-story") == ""


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


def test_settlement_prompt_commits_with_the_minted_story_identity() -> None:
    prompt = (
        Path(coder.__file__).parent / "main/prompts/settle-worktree.md"
    ).read_text(encoding="utf-8")

    assert "[{{ story_id }}]" in prompt
    assert "`Story: {{ story_id }}`" in prompt
    assert "`Story: {{ story_slug }}`" not in prompt


def test_every_story_commit_prompt_suffixes_the_subject_with_the_minted_id() -> None:
    prompts = Path(coder.__file__).parent
    offenders: list[str] = []
    for path in prompts.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "story_id') }}` as trailers" in text:
            expected = "[{{ workhorse_var('story_id') }}]"
        elif "`Story: {{ story_id }}` as" in text:
            expected = "[{{ story_id }}]"
        else:
            continue
        if expected not in text:
            offenders.append(str(path.relative_to(prompts)))

    assert offenders == []
