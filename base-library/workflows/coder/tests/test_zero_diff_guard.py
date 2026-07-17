"""Zero-diff churn guard (epic mode).

commit-story.py reports committed="no" when a "completed" story staged no
changes in any workspace repo. The guard (decide_committed → incr_zero_diff →
guard_zero_diff / reset_zero_diff) counts CONSECUTIVE no-op commits and halts
the run at max_zero_diff_commits (3) — a run whose stories keep "passing" QA
without landing any work is spinning, and continuing would grind the whole
queue through the same no-op machinery. A real commit resets the streak.

The zero-diff condition is driven by the git mock: ``git diff --cached
--quiet`` exiting 0 means nothing staged → committed="no".
"""
from __future__ import annotations

import subprocess

from workhorse.testing import WorkflowRun, assert_step_output

from conftest import (
    WORKFLOW,
    git_mock_no_remote,
    make_epic,
    make_queue,
    mock_all_agents_happy,
)


def _seed_zero_diff_repo(tmp_path, _story_mds: list) -> None:
    """Seed real git, then hide story status edits from the index.

    The workflow's QA side effect edits ``story.md``. Marking those tracked files
    assume-unchanged keeps the throwaway repo at zero diff without mocking ``git``.
    """
    git_mock_no_remote(tmp_path)
    exclude = tmp_path / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as f:
        f.write("\ndocs/**\n.workhorse-test/**\n")
    tracked_docs = subprocess.run(
        ["git", "ls-files", "docs"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for rel in tracked_docs:
        subprocess.run(
            ["git", "update-index", "--assume-unchanged", rel],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )


def _epic_with_stories(tmp_path, count: int) -> list:
    """One epic with ``count`` in-progress stories; returns their story.md paths."""
    slugs = [f"s-{i}" for i in range(1, count + 1)]
    make_epic(tmp_path, "epic-1", [{"slug": s, "status": "In progress"} for s in slugs])
    make_queue(tmp_path, ["epic-1"])
    return [
        tmp_path / "docs" / "epics" / "epic-1" / "stories" / s / "story.md"
        for s in slugs
    ]


def test_three_consecutive_zero_diff_commits_halt_the_run(tmp_path, monkeypatch):
    """3 stories in a row commit nothing → guard_zero_diff trips at 3 →
    zero_diff_give_up (fail terminal, exit 1) — the 4th story is never touched."""
    story_mds = _epic_with_stories(tmp_path, 4)
    _seed_zero_diff_repo(tmp_path, story_mds)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_all_agents_happy(wf, monkeypatch, story_md_paths=story_mds)

    result = wf.run()

    assert not result.passed(), "3 consecutive no-op commits must halt the run"
    assert result.exit_code == 1, f"expected fail exit 1, got {result.exit_code}"
    assert_step_output(result, "commit_story", "committed", "no")
    # The streak reached the literal threshold in guard_zero_diff (3)...
    assert_step_output(result, "incr_zero_diff", "zero_diff_count", {"value": 3})
    # ...so exactly 3 stories were processed before the halt — the 4th never ran.
    # One qa_interpret_and_explore call per story's QA phase (the happy path passes
    # first try), so the call count is the number of stories processed.
    qa_calls = [c for c in result.calls("claude") if c["node_id"] == "qa_interpret_and_explore"]
    assert len(qa_calls) == 3, f"expected 3 stories processed, got {len(qa_calls)}"


def test_below_threshold_zero_diffs_do_not_halt(tmp_path, monkeypatch):
    """Only 2 no-op commits (queue then exhausted) → the guard never trips and
    the run completes normally."""
    story_mds = _epic_with_stories(tmp_path, 2)
    _seed_zero_diff_repo(tmp_path, story_mds)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_all_agents_happy(wf, monkeypatch, story_md_paths=story_mds)

    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "incr_zero_diff", "zero_diff_count", {"value": 2})


def test_real_commit_resets_the_streak(tmp_path, monkeypatch):
    """committed="yes" routes through reset_zero_diff, zeroing the counter —
    the guard only ever counts CONSECUTIVE no-ops."""
    story_mds = _epic_with_stories(tmp_path, 1)
    git_mock_no_remote(tmp_path)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_all_agents_happy(wf, monkeypatch, story_md_paths=story_mds)

    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "commit_story", "committed", "yes")
    assert_step_output(result, "reset_zero_diff", "zero_diff_count", {"value": 0})
