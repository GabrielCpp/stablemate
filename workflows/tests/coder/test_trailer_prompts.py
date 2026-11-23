"""The commit prompts keep `Story:` in the last trailer block, where git reads it."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler.book.sources import story_commits

from workhorse_workflows import coder

Git = Callable[..., subprocess.CompletedProcess[str]]

PROMPTS = [
    "dev/prompts/_dev-rules.md",
    "qa/prompts/qa-story.md",
    "fix/prompts/fix-item.md",
    "main/prompts/replan-epic.md",
    "fix_ci/prompts/fix-ci.md",
]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_the_commit_prompt_asks_for_one_trailer_block(prompt: str) -> None:
    text = " ".join((Path(coder.__file__).parent / prompt).read_text(encoding="utf-8").split())

    assert "one trailer block" in text, prompt
    assert "no blank line" in text, prompt


def test_a_story_trailer_in_the_last_block_with_a_co_author_is_found(repo: Path, git: Git) -> None:
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "x.txt")
    git(
        repo,
        "commit",
        "-qm",
        "feat: change\n\nEpic: E\nStory: S\nCo-Authored-By: x <x@example.com>",
    )

    assert len(story_commits(str(repo), "S", base)) == 1


def test_a_story_trailer_followed_by_a_blank_line_and_a_co_author_is_lost(repo: Path, git: Git) -> None:
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "x.txt")
    git(
        repo,
        "commit",
        "-qm",
        "feat: change\n\nEpic: E\nStory: S\n\nCo-Authored-By: x <x@example.com>",
    )

    assert story_commits(str(repo), "S", base) == []
