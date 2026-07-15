"""Tests for validate-story.py — the bare-minimum per-story contract gate.

This validator is unchanged by the OKF migration: it only reads ``story.md`` (stdlib only, no
ostler). A story is intentionally lean — Context + Acceptance Criteria (plus the
``- **Status**:`` line the coder selector parses), and no open questions. The validator enforces
only that; depth lives in the coder workflow, and any repo-specific rule lives in that repo's
author flavor, not in this shared script.
"""
from __future__ import annotations

from conftest import run_script, write_story

# story.md bodies below carry their own front-matter so the gate sees a complete file.
_FM = "---\ntype: story\nslug: s1\nstatus: not_started\n---\n"


def test_good_minimal_story_passes(tmp_path):
    sd = write_story(tmp_path, "e1", "s1")
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "yes", out["story_errors"]


def test_missing_status_line_fails(tmp_path):
    body = _FM + "# Story\n\n## Context\n- goal\n\n## Acceptance Criteria\n- the page works\n"
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "Status" in out["story_errors"]


def test_missing_context_section_fails(tmp_path):
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Acceptance Criteria\n- the page works\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "Context" in out["story_errors"]


def test_missing_acceptance_section_fails(tmp_path):
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Context\n- bring surface to parity\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "Acceptance" in out["story_errors"]


def test_empty_acceptance_section_fails(tmp_path):
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Context\n- bring surface to parity\n\n## Acceptance Criteria\n\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "Acceptance" in out["story_errors"]


def test_plain_acceptance_criteria_need_no_gap_trace(tmp_path):
    # The minimal contract drops gap-tracing: a plain, user-facing AC is valid on its own.
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Context\n- bring the editor to parity with legacy\n"
        "## Acceptance Criteria\n- The page shows the same sections as the legacy editor.\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "yes", out["story_errors"]


def test_open_question_phrase_fails(tmp_path):
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Context\n- parity work\n"
        "## Acceptance Criteria\n"
        "- Content width: MUI lg vs Bootstrap 1170 is ≈parity — accept, or tune.\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "open question" in out["story_errors"].lower()


def test_todo_marker_fails_but_dotted_filename_is_clean(tmp_path):
    # A bare TODO is rejected; a "epics-todo.json" reference must NOT trip the guarded word match.
    body = (
        _FM + "# Story\n\n## Implementation Status\n- **Status**: Not started\n"
        "## Context\n- referenced in docs/epics/epics-todo.json\n"
        "## Acceptance Criteria\n- the page works\n- TODO decide later\n"
    )
    sd = write_story(tmp_path, "e1", "s1", body=body)
    out = run_script("validate-story.py", str(sd), repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "TODO" in out["story_errors"]
    assert "epics-todo.json" not in out["story_errors"]


def test_missing_file(tmp_path):
    (tmp_path / "docs/epics/e1/stories/s1").mkdir(parents=True)
    out = run_script("validate-story.py", "docs/epics/e1/stories/s1", repo=tmp_path)
    assert out["story_ok"] == "no"
    assert "story.md missing" in out["story_errors"]
