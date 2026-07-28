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


def run_select_epic(root: Path, run_dir: str = "") -> dict:
    """Invoke select-next-epic.py the way the ``select_epic`` node does and return its JSON.

    ``run_dir`` is argv[2] — the run directory holding the per-run blocked set
    (``blocked-epics.txt``). Empty (the default) means no set, as on a fresh run.
    """
    proc = subprocess.run(
        [sys.executable, str(_SELECT_EPIC), "", run_dir],
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def write_blocked(run_dir: Path, epics: list[str]) -> Path:
    """Seed the per-run blocked set flag-epic-blocked.py writes."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "blocked-epics.txt"
    path.write_text("".join(f"{e}\n" for e in epics), encoding="utf-8")
    return path


def test_empty_queue_returns_no_epic(tmp_path):
    """Empty epics-todo.json → has_epic=no, workflow exits 0 (no work)."""
    make_queue(tmp_path, [])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_epic", "has_epic", "no")


def test_missing_todo_file_returns_no_epic(tmp_path):
    """Missing epics-todo.json → select_epic returns has_epic=no with a reason."""
    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
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


def test_blocked_epic_is_skipped(tmp_path):
    """An epic in the per-run blocked set is passed over — the queue keeps moving.

    Without this, ``flag_epic_blocked`` would hand the same stuck epic straight back
    to ``select_epic`` and the run would spin on it (caught only by the gas tank),
    never reaching the independent epics queued behind it.
    """
    make_epic(tmp_path, "epic-front", [{"slug": "s-1", "status": "In progress"}])
    make_epic(tmp_path, "epic-back", [{"slug": "s-2", "status": "In progress"}])
    make_queue(tmp_path, ["epic-front", "epic-back"])
    run_dir = tmp_path / ".runs" / "coder-1"
    write_blocked(run_dir, ["epic-front"])

    out = run_select_epic(tmp_path, str(run_dir))

    assert out["has_epic"] == "yes"
    assert out["epic"] == "epic-back"


def test_all_blocked_returns_no_epic_with_queue_intact(tmp_path):
    """Every queued epic set aside → has_epic=no, and the queue is left untouched.

    This is the run's only clean stopping point when nothing can advance: it must be
    distinguishable from a drained queue, so the reason says the epics were set aside
    and nothing was merged.
    """
    make_epic(tmp_path, "epic-front", [{"slug": "s-1", "status": "In progress"}])
    make_epic(tmp_path, "epic-back", [{"slug": "s-2", "status": "In progress"}])
    queue = make_queue(tmp_path, ["epic-front", "epic-back"])
    run_dir = tmp_path / ".runs" / "coder-1"
    write_blocked(run_dir, ["epic-front", "epic-back"])

    out = run_select_epic(tmp_path, str(run_dir))

    assert out["has_epic"] == "no"
    assert "set aside" in out["reason"], out["reason"]
    # The queue itself is untouched: a later run retries both from the front.
    assert json.loads(queue.read_text(encoding="utf-8")) == ["epic-front", "epic-back"]


def test_missing_blocked_file_is_a_no_op(tmp_path):
    """A run dir with no blocked-epics.txt (the first pass of every run) blocks nothing."""
    make_epic(tmp_path, "epic-front", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-front"])
    run_dir = tmp_path / ".runs" / "coder-1"
    run_dir.mkdir(parents=True)

    out = run_select_epic(tmp_path, str(run_dir))

    assert out["has_epic"] == "yes"
    assert out["epic"] == "epic-front"
