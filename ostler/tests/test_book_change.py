"""A story's change is its own commits plus the uncommitted work, read from the `Story:` trailer."""

from __future__ import annotations

from pathlib import Path

from book_fakes import code_repo, commit_files, git
from ostler.book.change import Reading, Span, change_in, text_at
from ostler.book.sources import EMPTY_TREE, story_commits


def story(name: str) -> str:
    return f"feat: {name}\n\nStory: ACME-1"


def full(where: Path, rev: str) -> str:
    return git(where, "rev-parse", rev).strip()


def test_story_commits_follow_the_trailer_not_the_body(tmp_path):
    where = tmp_path / "app"
    code_repo(where, {"a.py": "a = 1\n"})
    mine = commit_files(where, {"a.py": "a = 2\n"}, story("one"))
    commit_files(where, {"a.py": "a = 3\n"}, "fix: see ACME-1\n\nbody says Story: ACME-1 in prose")
    commit_files(where, {"a.py": "a = 4\n"}, "feat: other\n\nStory: ACME-2")
    assert story_commits(str(where), "ACME-1") == [full(where, mine)]


def test_story_commits_after_since_only(tmp_path):
    where = tmp_path / "app"
    code_repo(where, {"a.py": "a = 1\n"})
    first = commit_files(where, {"a.py": "a = 2\n"}, story("one"))
    second = commit_files(where, {"a.py": "a = 3\n"}, story("two"))
    assert story_commits(str(where), "ACME-1", first) == [full(where, second)]
    assert story_commits(str(where), "ACME-1") == [full(where, first), full(where, second)]


def test_a_file_two_story_commits_touched_spans_the_parent_of_the_first_to_the_last(tmp_path):
    where = tmp_path / "app"
    base = code_repo(where, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
    commit_files(where, {"a.py": "a = 2\n"}, story("one"))
    commit_files(where, {"b.py": "b = 2\n"}, "feat: other\n\nStory: ACME-2")
    last = commit_files(where, {"a.py": "a = 3\n"}, story("two"))
    found = change_in(str(where), Reading(story="ACME-1"), (".",))
    assert found.spans == {"a.py": Span(full(where, base), full(where, last))}
    assert len(found.commits) == 2
    assert found.untracked == []


def test_a_dirty_file_spans_to_the_working_tree(tmp_path):
    where = tmp_path / "app"
    base = code_repo(where, {"a.py": "a = 1\n", "b.py": "b = 1\n"})
    commit_files(where, {"a.py": "a = 2\n"}, story("one"))
    (where / "a.py").write_text("a = 9\n")
    (where / "b.py").write_text("b = 9\n")
    (where / "c.py").write_text("c = 1\n")
    found = change_in(str(where), Reading(story="ACME-1"), (".",))
    assert found.spans == {"a.py": Span(full(where, base), None), "b.py": Span("HEAD", None)}
    assert found.untracked == ["c.py"]
    assert text_at(str(where), None, "a.py") == "a = 9\n"
    assert text_at(str(where), found.spans["a.py"].old, "a.py") == "a = 1\n"


def test_a_file_the_root_commit_added_starts_at_the_empty_tree(tmp_path):
    where = tmp_path / "app"
    where.mkdir()
    git(where, "init", "--quiet")
    last = commit_files(where, {"a.py": "a = 1\n"}, story("one"))
    found = change_in(str(where), Reading(story="ACME-1"), (".",))
    assert found.spans == {"a.py": Span(EMPTY_TREE, full(where, last))}
    assert text_at(str(where), EMPTY_TREE, "a.py") is None
