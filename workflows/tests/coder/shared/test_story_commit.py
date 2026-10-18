"""The story commit renders the repo's agent files first, so a skill the library changed since the last render does not refuse it."""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared import story_commit


def test_the_agent_files_are_rendered_before_the_story_commit_so_their_drift_is_not_refused(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drift = write(repo / ".drifted", "stale skill\n")
    hook = write(
        repo / ".git" / "hooks" / "pre-commit",
        f"#!{sys.executable}\nimport pathlib, sys\nsys.exit(1 if pathlib.Path({str(drift)!r}).exists() else 0)\n",
    )
    hook.chmod(0o755)
    write(repo / "feature.py", "VALUE = 1\n")

    def _render(root: Path) -> str:
        (root / ".drifted").unlink(missing_ok=True)
        return ""

    monkeypatch.setattr(story_commit, "render_agent_files_returning_failure", _render)

    result = story_commit.commit_story(
        logger,
        story_slug="the-story",
        repo_dir=str(repo),
        roots=[str(repo)],
    )

    assert result.committed
    assert "the-story" in git(repo, "log", "-1", "--format=%s").stdout
