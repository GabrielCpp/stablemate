"""Tests for the select-next-story script (via epic mode workflow).

select-next-story handles STORY selection only (epic selection is select-next-epic,
covered in test_select_epic.py). Most tests drive the workflow in epic mode — so
select_epic picks the epic, branch_epic cuts it, then select_story picks the next
runnable story WITHIN that epic — and assert on the ``select_story`` node outputs:
  - has_story="no"  → the epic's story loop is finished → open_pr → CI gate → merge
                       → prune_epic → select_epic → done (offline: all pass-through).

Selection ORDER (which story is picked *first* given dependencies) can't be inspected
by driving the whole workflow: the operator gate no longer exits — it blocks in place
to keep the container (and its groom sidecar) alive — so there is no early-stop that
freezes the run right after the first ``select_story``. Those cases invoke
``select-next-story.py`` directly, which is exactly the unit under test.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workhorse.testing import WorkflowRun, assert_step_output, assert_json_file

from conftest import (
    WORKFLOW,
    make_epic,
    make_queue,
    git_mock_no_remote,
)

_SELECT_STORY = Path(__file__).resolve().parent.parent / "scripts" / "select-next-story.py"


def run_select_story(root: Path, epic: str) -> dict:
    """Invoke select-next-story.py the way the ``select_story`` node does and return its JSON.

    Epic-mode ``select_story`` calls the script with (epic, docs_path="", run_dir=""),
    resolving the docs root from ``AGENT_REPO_DIR`` — so this mirrors the node without
    needing the full workflow (whose operator gate would otherwise block).
    """
    proc = subprocess.run(
        [sys.executable, str(_SELECT_STORY), epic, "", ""],
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_selects_first_incomplete_story(tmp_path):
    """A queue with one incomplete story → has_story=yes, slug and epic set."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])

    out = run_select_story(tmp_path, "epic-1")

    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s-1"
    assert out["epic"] == "epic-1"


def test_skips_completed_story_returns_no_story(tmp_path):
    """A story with 'QA passed' status → select_story returns has_story=no."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "QA passed (2026-01-01)."}])
    make_queue(tmp_path, ["epic-1"])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), result.stderr
    assert_step_output(result, "select_story", "has_story", "no")


def test_prunes_completed_epic_from_queue(tmp_path):
    """All stories in an epic done → epic is removed from epics-todo.json."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "QA passed (2026-01-01)."}])
    make_queue(tmp_path, ["epic-1"])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), result.stderr
    assert_json_file(tmp_path, "docs/epics/epics-todo.json", [])


def test_missing_dependencies_json_returns_no_story(tmp_path):
    """Epic directory exists but has no dependencies.json → has_story=no + reason."""
    epic_dir = tmp_path / "docs" / "epics" / "epic-1"
    epic_dir.mkdir(parents=True)
    make_queue(tmp_path, ["epic-1"])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), result.stderr
    assert_step_output(result, "select_story", "has_story", "no")
    outputs = result.step_outputs("select_story")
    assert "dependencies.json" in outputs.get("reason", ""), (
        f"Expected reason to mention dependencies.json, got: {outputs.get('reason')}"
    )


def test_dependency_order_respected(tmp_path):
    """Story with an unmet dependency is not selected before its prerequisite."""
    make_epic(
        tmp_path,
        "epic-1",
        [
            {"slug": "s-2", "status": "In progress", "deps": ["s-1"]},
            {"slug": "s-1", "status": "In progress"},
        ],
    )
    make_queue(tmp_path, ["epic-1"])

    # s-1 must be selected first because s-2 depends on it, regardless of list order.
    out = run_select_story(tmp_path, "epic-1")
    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s-1"


def test_unauthored_next_story_ends_epic_loop(tmp_path):
    """A story listed in dependencies.json but with no story.md (unauthored) →
    has_story=no, which ends the epic's story loop (PR + merge + advance) rather
    than dead-ending the whole run. The reason names the missing story.md."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    # Simulate an unauthored story: drop its story.md (dependencies.json still lists it).
    (tmp_path / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "story.md").unlink()

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_story", "has_story", "no")
    outputs = result.step_outputs("select_story")
    assert "story.md" in outputs.get("reason", ""), (
        f"Expected reason to mention the missing story.md, got: {outputs.get('reason')}"
    )
