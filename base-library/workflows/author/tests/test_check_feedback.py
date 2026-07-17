"""Tests for check_feedback.py — the non-blocking per-story feedback poll.

Unlike await-operator.py it must NEVER exit non-zero, and it consumes NEW exactly
once. Uses the shared subprocess helper (AGENT_REPO_DIR → sandbox)."""
from __future__ import annotations

import json

from conftest import run_script_raw

INBOX = "docs/epics/e1/stories/s1/feedback.md"


def _mk(repo, body):
    p = repo / INBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_is_absent_exit0(tmp_path):
    proc = run_script_raw("check_feedback.py", INBOX, repo=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["feedback"]["present"] == "no"


def test_new_is_present_and_consumed(tmp_path):
    inbox = _mk(tmp_path, "STATUS: NEW\nSCOPE: epic\n\n## Feedback\nSplit this story in two.\n")
    proc = run_script_raw("check_feedback.py", INBOX, repo=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)["feedback"]
    assert out["present"] == "yes" and out["scope"] == "epic"
    assert "Split this story in two." in out["content"]
    assert "CONSUMED" in inbox.read_text() and "STATUS: NEW" not in inbox.read_text()


def test_consumed_then_absent(tmp_path):
    _mk(tmp_path, "STATUS: NEW\n\n## Feedback\none-shot.\n")
    assert json.loads(run_script_raw("check_feedback.py", INBOX, repo=tmp_path).stdout)["feedback"]["present"] == "yes"
    assert json.loads(run_script_raw("check_feedback.py", INBOX, repo=tmp_path).stdout)["feedback"]["present"] == "no"


def test_no_status_with_content_is_new(tmp_path):
    _mk(tmp_path, "Reuse the existing layout; do not invent a new one.\n")
    out = json.loads(run_script_raw("check_feedback.py", INBOX, repo=tmp_path).stdout)["feedback"]
    assert out["present"] == "yes"


def test_whitespace_only_is_absent(tmp_path):
    _mk(tmp_path, "  \n\n")
    assert json.loads(run_script_raw("check_feedback.py", INBOX, repo=tmp_path).stdout)["feedback"]["present"] == "no"
