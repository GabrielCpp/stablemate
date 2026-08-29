"""Tests for ostler path subcommand (slug → canonical path resolution)."""

from __future__ import annotations

from ostler import crud
from ostler.model import load
from ostler.path import resolve_branch, resolve_spec, resolve_story


def test_resolve_spec(repo):
    graph = load(repo)
    assert resolve_spec(graph, "CASE-1234") == "docs/specs/CASE-1234"


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
    # The id is the directory key, whichever name the caller held.
    assert resolve_spec(graph, "01-foo") == f"docs/specs/{story.eid}"
    assert resolve_spec(graph, story.eid) == f"docs/specs/{story.eid}"


def test_resolve_spec_keeps_a_spec_already_on_disk_under_the_slug(tmp_path):
    graph, story = _minted_story(tmp_path)
    (tmp_path / "docs" / "specs" / "01-foo").mkdir(parents=True)
    assert resolve_spec(graph, "01-foo") == "docs/specs/01-foo"
    # Once the id-keyed dir exists, it wins again.
    (tmp_path / "docs" / "specs" / story.eid).mkdir()
    assert resolve_spec(graph, "01-foo") == f"docs/specs/{story.eid}"


def test_find_story_answers_to_the_minted_id(tmp_path):
    graph, story = _minted_story(tmp_path)
    assert graph.find_story(story.eid) == graph.find_story("01-foo")


def test_resolve_spec_uses_doc_roots(repo):
    graph = load(repo)
    assert resolve_spec(graph, "01-foo") == "docs/specs/01-foo"


def test_resolve_story(repo):
    graph = load(repo)
    assert resolve_story(graph, "epic-a", "01-foo") == "docs/epics/epic-a/stories/01-foo/story.md"


def test_resolve_branch_story():
    # Bare id, no prefix — the id is already globally unique.
    assert resolve_branch("CASE-1234") == "CASE-1234"


def test_resolve_branch_epic():
    assert resolve_branch("my-epic", epic=True) == "feat/my-epic"
