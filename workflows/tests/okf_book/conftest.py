"""Fixtures that give every test a git identity, and keep farrier out."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared import book_flow

@pytest.fixture(autouse=True)
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in (
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@example.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@example.com"),
    ):
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def rendered_repos(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The repos a book commit rendered the agent files of, with farrier itself left out of every test."""
    rendered: list[Path] = []

    def _render(root: Path) -> str:
        rendered.append(root)
        return ""

    monkeypatch.setattr(book_flow, "render_agent_files_returning_failure", _render)
    return rendered


@pytest.fixture(autouse=True)
def declared_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A book commit meets no declared commit check unless a test says which."""

    def _passes(_root: Path, _message: str, _pathspecs: tuple[str, ...]) -> str:
        return ""

    monkeypatch.setattr(book_flow, "declared_checks_failure", _passes)
