"""Tests for hang-report.py — the cap-wait-aware hang detector.

The one property that must hold: a node that slept for hours on a usage cap is NEVER flagged
as a hang, while a node that did hours of ACTIVE work is. Everything else is presentation.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "hang_report", Path(__file__).parent / "hang-report.py")
hr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hr)


def _run_dir(tmp_path: Path, node: str, *, enter: str, done: str, flow: bool = False) -> Path:
    """Write one events.jsonl with a single node enter/done pair."""
    base = tmp_path / "artifacts" / "run1"
    d = base / node / "_flow" if flow else base
    d.mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text(
        json.dumps({"ts": enter, "phase": "enter", "node": node}) + "\n"
        + json.dumps({"ts": done, "phase": "done", "node": node}) + "\n",
        encoding="utf-8")
    return base


def test_cap_wait_is_never_flagged_as_a_hang(tmp_path: Path):
    """A node with 3h of wall-clock that was 3h of cap-wait + 2min of work is healthy."""
    art = _run_dir(tmp_path, "review_story_documentation",
                   enter="2026-07-21T00:00:00+00:00", done="2026-07-21T03:35:00+00:00")
    logs = tmp_path / "logs"
    logs.mkdir()
    # The agent runner's cap-sleep line, stating the pause length for this node.
    (logs / "coder.log").write_text(
        "[review_story_documentation] ⏸ spending/usage cap reached — pausing ~12900s (resuming …)\n",
        encoding="utf-8")

    total, runs, longest = hr.node_totals(str(art))
    cap = hr.cap_wait_by_node(str(logs))
    assert runs["review_story_documentation"] == 1
    # ~3h35m wall, ~3h35m of it cap-wait → active ≈ a few minutes, well under any threshold.
    active = total["review_story_documentation"] - min(cap["review_story_documentation"],
                                                       total["review_story_documentation"])
    assert active < 600, f"cap-wait must be subtracted; active={active}s"


def test_genuine_active_work_is_flagged(tmp_path: Path):
    """A node doing 2h of ACTIVE work (no cap-wait) is a real hang/churn."""
    art = _run_dir(tmp_path, "stuck_agent",
                   enter="2026-07-21T00:00:00+00:00", done="2026-07-21T02:00:00+00:00")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "coder.log").write_text("no cap here\n", encoding="utf-8")

    total, runs, _ = hr.node_totals(str(art))
    cap = hr.cap_wait_by_node(str(logs))
    active_per_run = (total["stuck_agent"] - cap.get("stuck_agent", 0)) / runs["stuck_agent"]
    assert active_per_run >= 1800, "2h of active work must exceed the 30-min hang threshold"


def test_flow_containers_are_excluded(tmp_path: Path):
    """A flow container's time is its children's — flagging it points at the wrong node."""
    base = tmp_path / "artifacts" / "run1"
    # qa_phase is a container (owns _flow/events.jsonl); plan_qa is a leaf inside it.
    (base / "qa_phase" / "_flow").mkdir(parents=True)
    (base / "qa_phase" / "_flow" / "events.jsonl").write_text(
        json.dumps({"ts": "2026-07-21T00:00:00+00:00", "phase": "enter", "node": "plan_qa"}) + "\n"
        + json.dumps({"ts": "2026-07-21T00:02:00+00:00", "phase": "done", "node": "plan_qa"}) + "\n",
        encoding="utf-8")
    assert "qa_phase" in hr.flow_containers(str(base))
    assert "plan_qa" not in hr.flow_containers(str(base))
