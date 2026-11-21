"""The change a reading of the repository names: a range from a commit to the working tree, or the commits of one story with the uncommitted work."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ostler.book.sources import EMPTY_TREE, Window, changed_in_tree, git, story_commits


@dataclass(frozen=True)
class Span:
    old: str
    new: str | None


@dataclass
class Change:
    spans: dict[str, Span] = field(default_factory=dict)
    untracked: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Reading:
    base: str = ""
    story: str = ""
    since: str | None = None


def touched_by(root: str, commit: str, specs: tuple[str, ...] | list[str]) -> list[str]:
    out = git(root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "--relative", "--root", commit, "--", *specs)
    return [line for line in out.splitlines() if line]


def parent_of(root: str, commit: str) -> str:
    try:
        return git(root, "rev-parse", "--verify", "--quiet", f"{commit}^").strip()
    except subprocess.CalledProcessError:
        return EMPTY_TREE


def change_since(root: str, base: str, specs: tuple[str, ...] | list[str]) -> Change:
    tracked, untracked = changed_in_tree(root, base, tuple(specs))
    return Change({path: Span(base, None) for path in tracked}, untracked)


def change_of(root: str, commits: list[str], specs: tuple[str, ...] | list[str], uncommitted: bool = True) -> Change:
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for commit in commits:
        for path in touched_by(root, commit, specs):
            first.setdefault(path, commit)
            last[path] = commit
    spans = {path: Span(parent_of(root, first[path]), last[path]) for path in first}
    if not uncommitted:
        return Change(spans, [], list(commits))
    tracked, untracked = changed_in_tree(root, "HEAD", tuple(specs))
    for path in tracked:
        spans[path] = Span(spans[path].old if path in spans else "HEAD", None)
    return Change(spans, untracked, list(commits))


def resolved_since(root: str, since: str | None) -> str | None:
    if not since:
        return None
    try:
        return git(root, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        return None


def change_in(root: str, reading: Reading, specs: tuple[str, ...] | list[str]) -> Change:
    if not reading.story:
        return change_since(root, reading.base, specs)
    return change_of(root, story_commits(root, reading.story, resolved_since(root, reading.since)), specs)


def story_window(root: str, story: str, since: str | None, specs: tuple[str, ...]) -> Window | None:
    resolved = resolved_since(root, since)
    commits = story_commits(root, story, resolved)
    if not commits:
        return None
    origin = resolved or parent_of(root, commits[0])
    start = origin if origin == EMPTY_TREE else git(root, "rev-parse", "--short", origin).strip()
    spans = {path: (span.old, span.new) for path, span in change_of(root, commits, specs, uncommitted=False).spans.items() if span.new}
    return Window(story, start, frozenset(commits), spans)


def text_at(root: str, rev: str | None, path: str) -> str | None:
    if rev is None:
        try:
            return (Path(root) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    try:
        return git(root, "show", f"{rev}:./{path}")
    except subprocess.CalledProcessError:
        return None
