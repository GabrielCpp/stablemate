"""Tests for the non-blocking operator-feedback checkpoint.

Two layers:
  * Script state machine — check_feedback.py as a subprocess (it must NEVER exit
    non-zero, and must consume NEW exactly once).
  * Workflow wiring — with the coder WorkflowRun harness: feedback present routes
    one rework pass through apply_impl_feedback / apply_qa_feedback; feedback
    absent behaves exactly like the happy path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workhorse.testing import WorkflowRun

from conftest import WORKFLOW, git_mock_no_remote, mock_all_agents_happy, story_params

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_feedback.py"
INBOX = "docs/specs/s-1/feedback.md"


# --------------------------------------------------------------------------- #
# Script state machine (subprocess; never halts)                              #
# --------------------------------------------------------------------------- #

def _run(repo: Path, arg: str = INBOX) -> subprocess.CompletedProcess:
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    return subprocess.run(
        [sys.executable, str(SCRIPT), arg],
        capture_output=True, text=True, env=env,
    )


def _mk(repo: Path, body: str) -> Path:
    p = repo / INBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_file_reports_absent(tmp_path):
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["feedback"]["present"] == "no"


def test_new_is_present_and_consumed(tmp_path):
    inbox = _mk(tmp_path, "STATUS: NEW\nSCOPE: story\n\n## Feedback\nPrefer approach X.\n")
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)["feedback"]
    assert out["present"] == "yes"
    assert out["scope"] == "story"
    assert "Prefer approach X." in out["content"]
    # Consumed in place so the next poll does not re-fire.
    assert "CONSUMED" in inbox.read_text()
    assert "STATUS: NEW" not in inbox.read_text()


def test_consumed_reports_absent(tmp_path):
    _mk(tmp_path, "STATUS: CONSUMED\n\n## Feedback\nold.\n")
    proc = _run(tmp_path)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["feedback"]["present"] == "no"


def test_second_poll_after_consume_is_absent(tmp_path):
    _mk(tmp_path, "STATUS: NEW\n\n## Feedback\none-shot.\n")
    assert json.loads(_run(tmp_path).stdout)["feedback"]["present"] == "yes"
    assert json.loads(_run(tmp_path).stdout)["feedback"]["present"] == "no"


def test_scope_epic_is_parsed(tmp_path):
    _mk(tmp_path, "STATUS: NEW\nSCOPE: epic\n\n## Feedback\nbroaden.\n")
    out = json.loads(_run(tmp_path).stdout)["feedback"]
    assert out["present"] == "yes" and out["scope"] == "epic"


def test_no_status_with_content_is_treated_as_new(tmp_path):
    inbox = _mk(tmp_path, "Please reuse the existing helper instead of a new client.\n")
    out = json.loads(_run(tmp_path).stdout)["feedback"]
    assert out["present"] == "yes"
    assert "CONSUMED" in inbox.read_text()


def test_whitespace_only_is_absent(tmp_path):
    _mk(tmp_path, "   \n\n")
    assert json.loads(_run(tmp_path).stdout)["feedback"]["present"] == "no"


def test_blank_arg_is_absent(tmp_path):
    proc = _run(tmp_path, arg="")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["feedback"]["present"] == "no"


# --------------------------------------------------------------------------- #
# Workflow wiring (coder story mode)                                          #
# --------------------------------------------------------------------------- #

def _write_inbox(sandbox: Path, body: str) -> Path:
    p = sandbox / "docs" / "specs" / "s-1" / "feedback.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_no_feedback_runs_like_happy_path(story_sandbox, monkeypatch):
    """With no feedback.md the checkpoints fall through — run completes, no rework node."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert [c for c in result.calls("claude") if c["node_id"] == "apply_impl_feedback"] == []
    assert [c for c in result.calls("claude") if c["node_id"] == "apply_qa_feedback"] == []


def test_impl_feedback_routes_one_rework_then_proceeds(story_sandbox, monkeypatch):
    """feedback.md present after implementation → apply_impl_feedback once → re-review → QA → done.

    The post-impl check consumes the feedback, so the post-QA check sees it CONSUMED
    and does not fire — exactly one rework cycle for one drop."""
    inbox = _write_inbox(story_sandbox, "STATUS: NEW\n\n## Feedback\nRename the field to `slug`.\n")
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    wf.mock_agent("apply_impl_feedback", {"impl_result": {"status": "applied", "notes": ""}})

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    impl_fb = [c for c in result.calls("claude") if c["node_id"] == "apply_impl_feedback"]
    assert len(impl_fb) == 1, f"expected 1 apply_impl_feedback call, got {len(impl_fb)}"
    assert [c for c in result.calls("claude") if c["node_id"] == "apply_qa_feedback"] == []
    assert "CONSUMED" in inbox.read_text()


def test_qa_feedback_routes_through_apply_qa_feedback(story_sandbox, monkeypatch):
    """Feedback dropped only at QA time → check_qa_feedback → apply_qa_feedback → re-QA → done.

    The feedback file must appear *during* the QA phase (so the post-impl check already
    passed without seeing it). The execution reviewer is ``assess_qa_run``, so its
    first invocation writes a NEW feedback.md; the second (after the rework re-QAs)
    writes nothing, so the loop terminates after exactly one rework.
    """
    inbox_rel = "docs/specs/s-1/feedback.md"
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    wf.mock_agent_sequence("assess_qa_run", [
        {
            "response": {"qa_assessment": {"disposition": "confirmed", "failure_class": "none", "objective_reached": "yes", "notes": ""}},
            "side_effects": [{"path": str(story_sandbox / inbox_rel),
                              "content": "STATUS: NEW\n\n## Feedback\nTighten the empty-state copy.\n"}],
        },
        {"response": {"qa_assessment": {"disposition": "confirmed", "failure_class": "none", "objective_reached": "yes", "notes": ""}}},
    ])
    wf.mock_agent("apply_qa_feedback", {"qa_result": {"status": "passed", "notes": ""}})

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    qa_fb = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_feedback"]
    assert len(qa_fb) == 1, f"expected 1 apply_qa_feedback call, got {len(qa_fb)}"
    assert "CONSUMED" in (story_sandbox / inbox_rel).read_text()
