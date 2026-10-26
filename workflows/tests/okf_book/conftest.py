"""Fixtures that give every test a git identity, keep farrier out, and stub the ostler-okf skill."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.support import MEMBER, MEMBER_FILE, MEMBER_FOLDER, MEMBER_SOURCE, Workspace
from workhorse.testing import make_git_repo

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


@pytest.fixture
def ostler_okf_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    skill = home / ".claude/skills/ostler-okf/SKILL.md"
    skill.parent.mkdir(parents=True)
    _ = skill.write_text("---\nname: ostler-okf\nmetadata:\n  name: ostler-okf\n---\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CLI", "claude")
    monkeypatch.chdir(tmp_path)
    return skill


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    member = tmp_path / "code" / MEMBER
    (member / MEMBER_FOLDER).mkdir(parents=True)
    _ = (member / MEMBER_FILE).write_text(MEMBER_SOURCE, encoding="utf-8")
    _ = (member / "agents.yml").write_text("qa:\n  tools:\n    - curl\n", encoding="utf-8")
    _ = make_git_repo(member, name=MEMBER)
    docs = make_git_repo(tmp_path / "artifacts-home", name="docs")
    config = tmp_path / "home.toml"
    _ = config.write_text(f'[workspaces]\nacme = ["{member}"]\n', encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(docs))
    monkeypatch.setenv("STABLEMATE_WORKSPACE", "acme")
    return Workspace(docs=docs.resolve(), member=member.resolve())
