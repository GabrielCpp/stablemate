"""Tests for ostler path subcommand (slug → canonical path resolution)."""

from __future__ import annotations

from conftest import FOO_ID, specs_root
import pytest

from ostler import crud
from ostler.model import load
from ostler.path import resolve_branch, resolve_spec, resolve_story


def test_resolve_spec(repo):
    graph = load(repo)
    assert resolve_spec(graph, "CASE-1234") == str(specs_root() / "CASE-1234")


def _minted_story(tmp_path):
    """A crud-created story, so it carries a real minted id in epic block and frontmatter."""
    crud.create_epic(load(tmp_path), "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "01-foo", "Foo")
    graph = load(tmp_path)
    found = graph.find_story("01-foo")
    assert found is not None
    return graph, found[1]


def test_resolve_spec_keys_by_the_minted_id(tmp_path):
    graph, story = _minted_story(tmp_path)
    assert story.eid
    assert resolve_spec(graph, "01-foo") == str(specs_root() / story.eid)
    assert resolve_spec(graph, story.eid) == str(specs_root() / story.eid)


def test_resolve_spec_ignores_a_slug_named_folder_on_disk(tmp_path):
    graph, story = _minted_story(tmp_path)
    (specs_root() / "01-foo").mkdir(parents=True)
    assert resolve_spec(graph, "01-foo") == str(specs_root() / story.eid)


def test_resolve_spec_refuses_a_story_with_no_id(repo):
    graph = load(repo)
    graph.epics[0].stories[0].eid = ""
    with pytest.raises(ValueError, match="01-foo.*no id"):
        resolve_spec(graph, "01-foo")


def test_resolve_spec_uses_an_unknown_argument_as_given(repo):
    assert resolve_spec(load(repo), "ABC") == str(specs_root() / "ABC")


def test_find_story_answers_to_the_minted_id(tmp_path):
    graph, story = _minted_story(tmp_path)
    assert graph.find_story(story.eid) == graph.find_story("01-foo")


def test_resolve_spec_uses_doc_roots(repo):
    graph = load(repo)
    assert resolve_spec(graph, "01-foo") == str(specs_root() / FOO_ID)


def test_resolve_story(repo):
    graph = load(repo)
    assert resolve_story(graph, "epic-a", "01-foo") == "docs/epics/epic-a/stories/01-foo/story.md"


def test_resolve_branch_story():
    assert resolve_branch("CASE-1234") == "CASE-1234"


def test_resolve_branch_epic():
    assert resolve_branch("my-epic", epic=True) == "feat/my-epic"
