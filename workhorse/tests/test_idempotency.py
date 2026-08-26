"""Tests for the checkpoint bookkeeping resume rests on.

Every checkpoint carries a monotonic `seq`, and a completion marker records the seq it
completed under. That pairing is what tells a marker left by *this* visit to a node from
a stale one left by an earlier loop visit — the distinction any resume rule needs, and
the reason the counter is restored rather than restarted when a run resumes.

Run: uv run python tests/test_idempotency.py   (or via pytest)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from workhorse.artifacts import ArtifactWriter


def _writer(tmp):
    return ArtifactWriter("research", Path(tmp), run_id="grammar-semantics")


def test_checkpoint_seq_increments():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("a", {}, inputs={})
        cp1 = json.loads((w.run_dir / "checkpoint.json").read_text())
        w.write_state_checkpoint("b", {}, inputs={})
        cp2 = json.loads((w.run_dir / "checkpoint.json").read_text())
        assert cp1["seq"] == 1 and cp2["seq"] == 2


def test_done_marker_records_current_seq_and_next():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("implement", {"x": 1}, inputs={})        # seq -> 1
        w.write_step("implement", "prompt", {"impl": "ok"}, {"x": 1, "impl": "ok"}, next_node="gate_check")
        done = w.read_done("implement")
        assert done == {"seq": 1, "next": "gate_check"}
        assert w.read_context_after("implement") == {"x": 1, "impl": "ok"}


def test_branch_writes_done_marker():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("route_gate", {}, inputs={})             # seq -> 1
        w.write_branch("route_gate", "gate_selection.gate_id", "G1", "implement")
        assert w.read_done("route_gate") == {"seq": 1, "next": "implement"}


def test_resume_restores_seq_so_new_checkpoints_dont_collide():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("a", {}, inputs={})
        w.write_state_checkpoint("b", {}, inputs={})                      # seq -> 2
        w2 = ArtifactWriter.resume(w.run_dir)
        assert w2._seq == 2
        w2.write_state_checkpoint("c", {}, inputs={})                     # must continue at 3
        assert json.loads((w2.run_dir / "checkpoint.json").read_text())["seq"] == 3


def test_done_marker_pins_the_seq_it_completed_under():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        # 'record' completed under checkpoint seq 1.
        w.write_state_checkpoint("record", {}, inputs={})
        w.write_step("record", "p", {"r": 1}, {"r": 1}, next_node="publish")
        assert w.read_done("record") == {"seq": 1, "next": "publish"}

        # A later visit to the same node checkpoints again, so the marker written
        # before is recognisably stale: its seq no longer matches the checkpoint's.
        w.write_state_checkpoint("record", {}, inputs={})
        cp = json.loads((w.run_dir / "checkpoint.json").read_text())
        stale = w.read_done("record")
        assert stale is not None and cp["seq"] == 2 and stale["seq"] == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
