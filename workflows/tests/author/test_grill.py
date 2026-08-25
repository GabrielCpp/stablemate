from __future__ import annotations

import logging
from pathlib import Path

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes.grill import resolve_grill_trigger


def _logger() -> logging.Logger:
    return logging.getLogger("test.author.grill")


def test_resolve_grill_trigger_finds_the_command_tagged_grill(repo: Path) -> None:
    command = repo / ".claude/commands/some-other.md"
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text(
        "---\ndescription: not it\nmetadata:\n  tags: [other]\n---\n\nbody\n",
        encoding="utf-8",
    )
    grill = repo / ".claude/commands/stablemate-grill.md"
    grill.write_text(
        "---\ndescription: grill\nmetadata:\n  tags: [grill]\n---\n\nbody\n",
        encoding="utf-8",
    )

    trigger = resolve_grill_trigger(_logger(), repo_dir=str(repo))

    assert trigger == "/stablemate-grill"


def test_resolve_grill_trigger_fails_loudly_when_nothing_is_tagged(repo: Path) -> None:
    (repo / ".claude/commands/stablemate-grill.md").unlink()

    with pytest.raises(WorkflowFailed, match="tags: \\[grill\\]"):
        resolve_grill_trigger(_logger(), repo_dir=str(repo))
