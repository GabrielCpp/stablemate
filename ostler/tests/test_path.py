"""Tests for ostler path subcommand (story id → canonical path resolution)."""

from __future__ import annotations

from conftest import FOO_ID, ostler_process, specs_root
import pytest

from ostler import crud
from ostler.model import load
from ostler.path import resolve_branch, resolve_spec, resolve_story


def _minted_story(tmp_path):
    """A crud-created story, so it carries a real minted id in epic block and frontmatter."""
    crud.create_epic(load(tmp_path), "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "01-foo", "Foo")
    graph = load(tmp_path)
    found = graph.story_by_slug("01-foo")
    assert found is not None
    return graph, found[1]


def test_resolve_spec_refuses_an_unknown_id(repo):
    with pytest.raises(ValueError, match="no story with id 'CASE-1234'"):
        resolve_spec(load(repo), "CASE-1234")


def test_resolve_spec_refuses_a_slug_and_names_the_id(repo):
    with pytest.raises(ValueError, match=f"story slug, not a story id.*{FOO_ID}"):
        resolve_spec(load(repo), "01-foo")


def test_resolve_spec_keys_by_the_minted_id(tmp_path):
    graph, story = _minted_story(tmp_path)
    assert story.eid
    assert resolve_spec(graph, story.eid) == str(specs_root() / story.eid)


def test_resolve_spec_ignores_a_slug_named_folder_on_disk(tmp_path):
    graph, story = _minted_story(tmp_path)
    (specs_root() / "01-foo").mkdir(parents=True)
    assert resolve_spec(graph, story.eid) == str(specs_root() / story.eid)
    with pytest.raises(ValueError, match=story.eid):
        resolve_spec(graph, "01-foo")


def test_a_story_with_no_id_is_unreachable(repo):
    graph = load(repo)
    graph.epics[0].stories[0].eid = ""
    assert graph.find_story("01-foo") is None
    assert graph.find_story("") is None
    with pytest.raises(ValueError, match="01-foo"):
        resolve_spec(graph, "01-foo")


def test_find_story_answers_only_to_the_minted_id(tmp_path):
    graph, story = _minted_story(tmp_path)
    assert graph.find_story(story.eid) == graph.story_by_slug("01-foo")
    assert graph.find_story("01-foo") is None


def test_resolve_spec_returns_the_id_folder(repo):
    graph = load(repo)
    assert resolve_spec(graph, FOO_ID) == str(specs_root() / FOO_ID)


def test_resolve_story(repo):
    graph = load(repo)
    assert resolve_story(graph, FOO_ID) == "docs/epics/epic-a/stories/01-foo/story.md"


def test_resolve_story_refuses_a_slug(repo):
    with pytest.raises(ValueError, match=FOO_ID):
        resolve_story(load(repo), "01-foo")


def test_resolve_branch_story(repo):
    assert resolve_branch(load(repo), FOO_ID) == "01-foo"


def test_resolve_branch_epic(repo):
    assert resolve_branch(load(repo), "my-epic", epic=True) == "feat/my-epic"


def test_path_spec_cli_refuses_a_slug_with_the_id_hint(repo):
    done = ostler_process(repo, "path", "spec", "01-foo")
    assert done.returncode == 1
    assert FOO_ID in done.stdout + done.stderr
