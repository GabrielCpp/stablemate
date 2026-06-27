"""Tests for ostler path subcommand (slug → canonical path resolution)."""

from __future__ import annotations

from ostler.model import load
from ostler.path import resolve_branch, resolve_spec, resolve_story


def test_resolve_spec(repo):
    graph = load(repo)
    assert resolve_spec(graph, "CASE-1234") == "docs/specs/CASE-1234"


def test_resolve_spec_uses_doc_roots(repo):
    graph = load(repo)
    assert resolve_spec(graph, "01-foo") == "docs/specs/01-foo"


def test_resolve_story(repo):
    graph = load(repo)
    assert resolve_story(graph, "epic-a", "01-foo") == "docs/epics/epic-a/stories/01-foo/story.md"


def test_resolve_branch_story():
    assert resolve_branch("CASE-1234") == "story/CASE-1234"


def test_resolve_branch_epic():
    assert resolve_branch("my-epic", epic=True) == "feat/my-epic"
