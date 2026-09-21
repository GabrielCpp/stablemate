"""Tests for the checkpoint bookkeeping resume rests on."""
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
        w.write_state_checkpoint("implement", {"x": 1}, inputs={})
        w.write_step("implement", "prompt", {"impl": "ok"}, {"x": 1, "impl": "ok"}, next_node="gate_check")
        done = w.read_done("implement")
        assert done == {"seq": 1, "next": "gate_check"}
        assert w.read_context_after("implement") == {"x": 1, "impl": "ok"}


def test_branch_writes_done_marker():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("route_gate", {}, inputs={})
        w.write_branch("route_gate", "gate_selection.gate_id", "G1", "implement")
        assert w.read_done("route_gate") == {"seq": 1, "next": "implement"}


def test_resume_restores_seq_so_new_checkpoints_dont_collide():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("a", {}, inputs={})
        w.write_state_checkpoint("b", {}, inputs={})
        w2 = ArtifactWriter.resume(w.run_dir)
        assert w2._seq == 2
        w2.write_state_checkpoint("c", {}, inputs={})
        assert json.loads((w2.run_dir / "checkpoint.json").read_text())["seq"] == 3


def test_done_marker_pins_the_seq_it_completed_under():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("record", {}, inputs={})
        w.write_step("record", "p", {"r": 1}, {"r": 1}, next_node="publish")
        assert w.read_done("record") == {"seq": 1, "next": "publish"}

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
