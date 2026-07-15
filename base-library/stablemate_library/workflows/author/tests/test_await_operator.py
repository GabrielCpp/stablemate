"""Tests for await-operator.py — the on-demand recorded-Q&A gate."""
from __future__ import annotations

import json

from conftest import run_script_raw

CTX = "docs/epics/_author-context.md"


def test_first_block_writes_context_and_halts(tmp_path):
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    proc = run_script_raw("await-operator.py", CTX, "Which plan?", "epics_rework_count", repo=tmp_path)
    assert proc.returncode == 2
    ctx = tmp_path / CTX
    assert ctx.is_file()
    assert "AWAITING_OPERATOR" in ctx.read_text()
    assert "Which plan?" in ctx.read_text()


def test_still_awaiting_halts(tmp_path):
    ctx = tmp_path / CTX
    ctx.parent.mkdir(parents=True)
    ctx.write_text("STATUS: AWAITING_OPERATOR\n\nq\n")
    proc = run_script_raw("await-operator.py", CTX, "q", repo=tmp_path)
    assert proc.returncode == 2


def test_answered_proceeds_and_resets_counter(tmp_path):
    ctx = tmp_path / CTX
    ctx.parent.mkdir(parents=True)
    ctx.write_text("STATUS: ANSWERED\n\nq\n\n## Your answers\nUse plan B.\n")
    proc = run_script_raw("await-operator.py", CTX, "q", "epics_rework_count", repo=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["operator_input"]["answered"] is True
    assert out["epics_rework_count"]["value"] == 0
    # The status flips to CONSUMED so a later re-block re-arms instead of looping.
    assert "CONSUMED" in ctx.read_text()


def test_consumed_reblock_rearms_and_halts(tmp_path):
    ctx = tmp_path / CTX
    ctx.parent.mkdir(parents=True)
    ctx.write_text("STATUS: CONSUMED\n\nold q\n")
    proc = run_script_raw("await-operator.py", CTX, "new q", repo=tmp_path)
    assert proc.returncode == 2
    text = ctx.read_text()
    assert "AWAITING_OPERATOR" in text
    assert "new q" in text


def test_proceed_without_counter_emits_only_operator_input(tmp_path):
    ctx = tmp_path / CTX
    ctx.parent.mkdir(parents=True)
    ctx.write_text("STATUS: ANSWERED\n\nanswer\n")
    proc = run_script_raw("await-operator.py", CTX, "q", repo=tmp_path)
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert "operator_input" in out
    assert len(out) == 1  # no counter key when none requested
