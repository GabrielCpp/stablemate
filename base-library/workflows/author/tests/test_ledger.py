"""Tests for ledger.py — the append-only attempts ledger (negative-constraint memory)."""
from __future__ import annotations

from conftest import run_script

LP = "docs/epics/e1/stories/s1/attempts.md"


def test_append_creates_ledger_and_emits_note(tmp_path):
    out = run_script("ledger.py", LP, "1", "missing Acceptance Criteria", repo=tmp_path)
    assert "missing Acceptance Criteria" in out["prior_attempts"]
    assert out["ledger"] == LP
    assert (tmp_path / LP).is_file()


def test_second_attempt_accumulates(tmp_path):
    run_script("ledger.py", LP, "1", "first failure", repo=tmp_path)
    out = run_script("ledger.py", LP, "2", "second failure", repo=tmp_path)
    assert "first failure" in out["prior_attempts"]
    assert "second failure" in out["prior_attempts"]
    assert "Attempt 1" in out["prior_attempts"] and "Attempt 2" in out["prior_attempts"]


def test_same_label_is_idempotent(tmp_path):
    run_script("ledger.py", LP, "1", "the failure", repo=tmp_path)
    out = run_script("ledger.py", LP, "1", "the failure again", repo=tmp_path)
    # re-running the same attempt (resumed node) must not duplicate the entry
    assert out["prior_attempts"].count("## Attempt 1") == 1
    assert "the failure again" not in out["prior_attempts"]


def test_empty_ledger_path_is_noop(tmp_path):
    out = run_script("ledger.py", "", "1", "x", repo=tmp_path)
    assert out["prior_attempts"] == ""
    assert out["ledger"] == ""
