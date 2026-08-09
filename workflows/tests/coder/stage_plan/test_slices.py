"""The deterministic gate between a proposed slicing and any work being done."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.stage_plan.inventory import headings, sibling_headings
from coder.stage_plan._support import (
    FIRST,
    PLAN_TEXT,
    SECOND,
    context_of,
    exists,
    prepared_of,
    slice_of,
    slicing,
)


def test_a_shell_comment_in_a_fenced_block_is_not_a_phase() -> None:
    text = "# Plan\n\n```bash\n# not a heading\nmake test\n```\n\n## Real\n"

    assert headings(text) == [(1, "Plan"), (2, "Real")]


def test_sibling_headings_stop_at_the_enclosing_section() -> None:
    text = PLAN_TEXT + "\n## Acceptance criteria\n\n### Criterion one\n"

    assert sibling_headings(text, FIRST) == [FIRST, SECOND]


def test_a_dropped_tail_phase_fails_before_any_work_starts(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    proposal = slicing(
        slice_of("first", FIRST, "src/first.txt"), headings=[FIRST]
    )

    with pytest.raises(WorkflowFailed, match="do not match the plan's own phase headings"):
        prepared_of(context, logger, proposal)


def test_slices_must_cover_every_declared_phase(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    proposal = slicing(slice_of("first", FIRST, "src/first.txt"))

    with pytest.raises(WorkflowFailed, match="exactly once and in plan order"):
        prepared_of(context, logger, proposal)


def test_a_slice_must_carry_the_phase_it_claims(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    hollow = slice_of("second", SECOND, "src/second.txt")
    hollow["body"] = "# Something else\n\nCreate `src/second.txt`.\n"
    proposal = slicing(slice_of("first", FIRST, "src/first.txt"), hollow)

    with pytest.raises(WorkflowFailed, match="does not carry"):
        prepared_of(context, logger, proposal)


def test_a_slicing_without_a_repository_gate_is_refused(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    proposal = slicing(
        slice_of("first", FIRST, "src/first.txt"),
        slice_of("second", SECOND, "src/second.txt"),
        final=[],
    )

    with pytest.raises(WorkflowFailed, match="repository-wide verification gate"):
        prepared_of(context, logger, proposal)


def test_the_final_gate_may_not_call_git_or_a_shell(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    proposal = slicing(
        slice_of("first", FIRST, "src/first.txt"),
        slice_of("second", SECOND, "src/second.txt"),
        final=[{"argv": ["git", "push"], "cwd": ".", "timeout_s": 30}],
    )

    with pytest.raises(WorkflowFailed):
        prepared_of(context, logger, proposal)


def test_a_valid_slicing_writes_one_digested_document_per_phase(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    context = context_of(tmp_path, repo, logger)
    proposal = slicing(
        slice_of("first", FIRST, "src/first.txt"),
        slice_of("second", SECOND, "src/second.txt"),
        final=[exists("src/first.txt")],
    )

    prepared = prepared_of(context, logger, proposal)

    assert [staged.id for staged in prepared.slices] == ["first", "second"]
    assert [staged.covers for staged in prepared.slices] == [[FIRST], [SECOND]]
    for staged in prepared.slices:
        body = Path(staged.path).read_text(encoding="utf-8")
        assert staged.covers[0] in body
        assert len({staged.digest for staged in prepared.slices}) == 2


def test_a_dirty_worktree_is_refused_before_the_slicing_turn(
    tmp_path: Path, repo: Path, origin: Path, logger: Any
) -> None:
    (repo / "stray.txt").write_text("uncommitted\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="clean worktree"):
        context_of(tmp_path, repo, logger)


def test_an_unpushed_head_is_refused_before_the_slicing_turn(
    tmp_path: Path, repo: Path, origin: Path, logger: Any, git: Any
) -> None:
    (repo / "landed.txt").write_text("committed\n", encoding="utf-8")
    git(repo, "add", "landed.txt")
    git(repo, "commit", "-qm", "chore: local only")

    with pytest.raises(WorkflowFailed, match="not local HEAD"):
        context_of(tmp_path, repo, logger)
