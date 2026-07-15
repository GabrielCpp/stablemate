"""Tests for the select-next-epic script (epic selection only).

select-next-epic owns EPIC selection — it returns the front of epics-todo.json and
knows nothing about stories (that's select-next-story, in test_select_story.py).
Most tests drive the workflow in epic mode and assert on the ``select_epic`` node.
Inspecting the *first* epic pick can't go through the workflow — the operator gate no
longer exits, it blocks to keep the container alive — so that case invokes
``select-next-epic.py`` directly, the unit under test.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workhorse.testing import WorkflowRun, assert_step_output

from conftest import (
    WORKFLOW,
    make_epic,
    make_queue,
    git_mock_no_remote,
)

_SELECT_EPIC = Path(__file__).resolve().parent.parent / "scripts" / "select-next-epic.py"


def run_select_epic(root: Path) -> dict:
    """Invoke select-next-epic.py the way the ``select_epic`` node does and return its JSON."""
    proc = subprocess.run(
        [sys.executable, str(_SELECT_EPIC), ""],
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_empty_queue_returns_no_epic(tmp_path):
    """Empty epics-todo.json → has_epic=no, workflow exits 0 (no work)."""
    make_queue(tmp_path, [])

    wf = WorkflowRun(WORKFLOW, tmp_path)
    wf.mock_command("git", git_mock_no_remote())
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_epic", "has_epic", "no")


def test_missing_todo_file_returns_no_epic(tmp_path):
    """Missing epics-todo.json → select_epic returns has_epic=no with a reason."""
    wf = WorkflowRun(WORKFLOW, tmp_path)
    wf.mock_command("git", git_mock_no_remote())
    result = wf.run()

    assert result.passed(), result.stderr
    assert_step_output(result, "select_epic", "has_epic", "no")
    outputs = result.step_outputs("select_epic")
    assert outputs.get("reason"), "Expected a non-empty reason for missing file"


def test_returns_front_epic(tmp_path):
    """With two epics queued, select_epic returns the FRONT one as the current epic."""
    make_epic(tmp_path, "epic-front", [{"slug": "s-1", "status": "In progress"}])
    make_epic(tmp_path, "epic-back", [{"slug": "s-2", "status": "In progress"}])
    make_queue(tmp_path, ["epic-front", "epic-back"])

    out = run_select_epic(tmp_path)

    assert out["has_epic"] == "yes"
    assert out["epic"] == "epic-front"
