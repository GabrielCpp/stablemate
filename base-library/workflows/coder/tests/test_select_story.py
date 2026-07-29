"""Tests for the select-next-story script (via epic mode workflow).

select-next-story handles STORY selection only (epic selection is select-next-epic,
covered in test_select_epic.py). Most tests drive the workflow in epic mode — so
select_epic picks the epic, branch_epic cuts it, then select_story picks the next
runnable story WITHIN that epic — and assert on the ``select_story`` node outputs.

The output that decides the epic's fate is ``story_outcome``, not ``has_story``:
  - ``story``   → build it.
  - ``done``    → every story is done → prune_epic → open_pr → CI gate → merge
                  → select_epic → done (offline: all pass-through).
  - ``blocked`` → stories remain but none is runnable → flag_epic_blocked → select_epic.
                  Nothing is merged and the epic keeps its place in the queue.
Both "done" and "blocked" report ``has_story="no"``, which is exactly why branching on
that alone merged an epic with 20 of 21 stories unbuilt.

Selection ORDER (which story is picked *first* given dependencies) can't be inspected
by driving the whole workflow: the operator gate no longer exits — it blocks in place
to keep the container (and its groom sidecar) alive — so there is no early-stop that
freezes the run right after the first ``select_story``. Those cases invoke
``select-next-story.py`` directly, which is exactly the unit under test.
"""
from __future__ import annotations

import importlib.util
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


def _load_select_story():
    """Import select-next-story.py in-process (hyphenated name → importlib) so its pure
    helpers can be unit-tested without spawning the whole workflow."""
    spec = importlib.util.spec_from_file_location("select_next_story", _SELECT_STORY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_select_story(root: Path, epic: str, run_dir: str = "") -> dict:
    """Invoke select-next-story.py the way the ``select_story`` node does and return its JSON.

    Epic-mode ``select_story`` calls the script with (epic, docs_path="", run_dir),
    resolving the docs root from ``AGENT_REPO_DIR`` — so this mirrors the node without
    needing the full workflow (whose operator gate would otherwise block). ``run_dir``
    carries the per-run skip set; empty (the default) means none, as on a fresh run.
    """
    proc = subprocess.run(
        [sys.executable, str(_SELECT_STORY), epic, "", run_dir],
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_progress_fields_snapshot_the_queue_for_telemetry():
    """The ostler report's done/total feed the shared worklist snapshot, so the dashboard
    reads "3/12" — the Phase-1 activity payoff. This is the join: counts → wf.activity."""
    mod = _load_select_story()
    report = {"state": "ready", "total": 12, "done": 3,
              "remaining": [f"s-{i}" for i in range(9)]}
    fields = mod._progress_fields(report)
    assert fields["progress"] == "3/12"
    assert fields["remaining_count"] == "9"


def test_progress_fields_are_empty_when_the_report_cannot_say():
    """A legacy/failed report (a bare string, or one without counts) yields empty progress
    — the label is then dropped, exactly like any unrenderable label."""
    mod = _load_select_story()
    assert mod._progress_fields("")["progress"] == ""
    # A report present but without counts → 0/0, nothing remaining (still a valid shape).
    assert mod._progress_fields({"state": "no-epic"})["progress"] == "0/0"


def test_qa_passed_in_prose_is_not_a_done_status(tmp_path):
    """"QA passed" written *about* a story does not make the story done.

    ``_is_done`` used to be ``"QA passed" in <whole story.md>``, so a Context paragraph saying
    the legacy behaviour "QA passed last release", or an acceptance criterion naming the phrase,
    silently marked the story built: it was skipped, and its dependents unblocked on work that
    never happened. The status is now read as the *field* (frontmatter, else the parsed
    ``- **Status**:`` bullet) and judged by ``ostler.select.is_done``.
    """
    mod = _load_select_story()
    story_md = tmp_path / "story.md"
    story_md.write_text(
        "# Story: s-1\n\n"
        "## Context\n\n- the legacy report QA passed in the 4.2 release; keep that behaviour\n\n"
        "## Implementation Status\n\n- **Status**: In progress\n",
        encoding="utf-8",
    )
    assert mod._is_done(story_md) is False

    story_md.write_text(
        "# Story: s-1\n\n## Implementation Status\n\n- **Status**: QA passed (2026-01-01).\n",
        encoding="utf-8",
    )
    assert mod._is_done(story_md) is True


def test_prose_mentioning_qa_passed_is_still_selected(tmp_path):
    """The same fact through the node: such a story is offered as work, not skipped."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    story_md = tmp_path / "docs/epics/epic-1/stories/s-1/story.md"
    story_md.write_text(
        "# Story: s-1\n\n"
        "## Context\n\n- the report QA passed before the rewrite; parity is the bar\n\n"
        "## Implementation Status\n\n- **Status**: In progress\n",
        encoding="utf-8",
    )

    out = run_select_story(tmp_path, "epic-1")

    assert out["has_story"] == "yes"
    assert out["story_slug"] == "s-1"


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
    """All stories in an epic done → story_outcome=done → epic removed from the queue.

    ``done`` is the ONE outcome that may prune and merge, so it is asserted alongside
    the pruning: the queue emptying is only correct because the epic actually finished.
    """
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "QA passed (2026-01-01)."}])
    make_queue(tmp_path, ["epic-1"])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), result.stderr
    assert_step_output(result, "select_story", "story_outcome", "done")
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


def test_unauthored_next_story_sets_the_epic_aside(tmp_path):
    """A story listed in dependencies.json but with no story.md (unauthored) →
    story_outcome=blocked: the epic is set aside for this run, not merged.

    Unauthored scope is the case that looks most like "finished" — there is nothing
    left to select — and merging on it ships an epic whose stories were never written.
    The reason names the missing story.md so the operator knows what to author.
    """
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    # Simulate an unauthored story: drop its story.md (dependencies.json still lists it).
    (tmp_path / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "story.md").unlink()

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_story", "has_story", "no")
    assert_step_output(result, "select_story", "story_outcome", "blocked")
    outputs = result.step_outputs("select_story")
    assert "story.md" in outputs.get("reason", ""), (
        f"Expected reason to mention the missing story.md, got: {outputs.get('reason')}"
    )
    # Not finished → not merged: the epic keeps its place in the queue.
    assert_json_file(tmp_path, "docs/epics/epics-todo.json", ["epic-1"])


def test_blocked_epic_is_set_aside_not_merged(tmp_path):
    """Stories remain but none is runnable → the epic is set aside, and the run ends.

    This is the regression the whole ``story_outcome`` split exists for: the epic still
    has unbuilt stories, so pruning it (and opening/merging its PR) would ship it as
    complete. Instead ``flag_epic_blocked`` records it, ``select_epic`` finds nothing
    runnable, and the run ends with the queue untouched.
    """
    # s-2 waits on s-1, which is not in the epic at all → nothing will ever satisfy it.
    make_epic(
        tmp_path,
        "epic-1",
        [{"slug": "s-2", "status": "In progress", "deps": ["s-1"]}],
    )
    make_queue(tmp_path, ["epic-1"])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_story", "story_outcome", "blocked")
    assert_step_output(result, "flag_epic_blocked", "epic_blocked", "yes")
    # The set aside is per-run state, written where select_epic reads it.
    blocked = (Path(result.run_dir) / "blocked-epics.txt").read_text(encoding="utf-8")
    assert blocked.split() == ["epic-1"], blocked
    # Nothing merged: the queue still names the epic for a later run.
    assert_json_file(tmp_path, "docs/epics/epics-todo.json", ["epic-1"])
    assert_step_output(result, "select_epic", "has_epic", "no")


def test_unmet_dependency_reports_blocked_with_the_waiting_slugs(tmp_path):
    """Direct invocation: the blocked reason names the stories that are still waiting.

    Driving the workflow proves the routing; this proves the diagnosis — an operator
    reading the run needs to know *which* stories are stuck, not just that some are.
    """
    make_epic(
        tmp_path,
        "epic-1",
        [
            {"slug": "s-1", "status": "QA passed (2026-01-01)."},
            {"slug": "s-2", "status": "In progress", "deps": ["s-missing"]},
            {"slug": "s-3", "status": "In progress", "deps": ["s-2"]},
        ],
    )
    make_queue(tmp_path, ["epic-1"])

    out = run_select_story(tmp_path, "epic-1")

    assert out["has_story"] == "no"
    assert out["story_outcome"] == "blocked"
    assert "s-2" in out["reason"] and "s-3" in out["reason"], out["reason"]


def test_all_remaining_stories_skipped_reports_blocked(tmp_path):
    """Every runnable story given up this run → blocked, not done.

    This is the exact shape of the observed failure: one story exhausts its QA rework
    budget, lands in the per-run skip set, and the epic then has nothing left to offer.
    Reporting ``done`` here is what merged an epic with its stories unbuilt.
    """
    make_epic(
        tmp_path,
        "epic-1",
        [
            {"slug": "s-1", "status": "QA passed (2026-01-01)."},
            {"slug": "s-2", "status": "In progress"},
        ],
    )
    make_queue(tmp_path, ["epic-1"])
    run_dir = tmp_path / ".runs" / "coder-1"
    run_dir.mkdir(parents=True)
    (run_dir / "qa-skip-stories.txt").write_text("s-2\n", encoding="utf-8")

    out = run_select_story(tmp_path, "epic-1", str(run_dir))

    assert out["has_story"] == "no"
    assert out["story_outcome"] == "blocked"
    assert "given up" in out["reason"], out["reason"]
