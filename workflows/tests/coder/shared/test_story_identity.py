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

from workhorse_workflows.coder.shared.dev import changed_files
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
