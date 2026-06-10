"""Tests for resume idempotency: a node that completed under the current checkpoint
is fast-forwarded (not re-run), while a stale completion marker from an earlier loop
visit is correctly ignored so the node re-runs.

Run: ./.venv/bin/python tests/test_idempotency.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path

from workhorse.artifacts import ArtifactWriter

m = importlib.import_module("workhorse.main")


def _writer(tmp):
    return ArtifactWriter("research", Path(tmp), run_id="grammar-semantics")


def test_checkpoint_seq_increments():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("a", {})
        cp1 = json.loads((w.run_dir / "checkpoint.json").read_text())
        w.write_checkpoint("b", {})
        cp2 = json.loads((w.run_dir / "checkpoint.json").read_text())
        assert cp1["seq"] == 1 and cp2["seq"] == 2


def test_done_marker_records_current_seq_and_next():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("implement", {"x": 1})        # seq -> 1
        w.write_step("implement", "prompt", {"impl": "ok"}, {"x": 1, "impl": "ok"}, next_node="gate_check")
        done = w.read_done("implement")
        assert done == {"seq": 1, "next": "gate_check"}
        assert w.read_context_after("implement") == {"x": 1, "impl": "ok"}


def test_branch_writes_done_marker():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("route_gate", {})             # seq -> 1
        w.write_branch("route_gate", "gate_selection.gate_id", "G1", "implement")
        assert w.read_done("route_gate") == {"seq": 1, "next": "implement"}


def test_resume_restores_seq_so_new_checkpoints_dont_collide():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("a", {})
        w.write_checkpoint("b", {})                      # seq -> 2
        w2 = ArtifactWriter.resume(w.run_dir)
        assert w2._seq == 2
        w2.write_checkpoint("c", {})                     # must continue at 3
        assert json.loads((w2.run_dir / "checkpoint.json").read_text())["seq"] == 3


def test_should_fast_forward_matches_only_current_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        # node 'record' completed under checkpoint seq 1
        w.write_checkpoint("record", {})
        w.write_step("record", "p", {"r": 1}, {"r": 1}, next_node="publish")
        done = w.read_done("record")               # {seq:1, next:publish}

        # killed AFTER record finished but before the cursor advanced:
        # checkpoint still points at 'record' with the SAME seq -> fast-forward.
        assert m._should_fast_forward(done, {"current_id": "record", "seq": 1}) is True

        # killed DURING a LATER visit to 'record' (checkpoint seq advanced to 5,
        # done marker is the stale seq 1) -> must re-run, not fast-forward.
        assert m._should_fast_forward(done, {"current_id": "record", "seq": 5}) is False

        # no marker at all (node never completed) -> re-run.
        assert m._should_fast_forward(None, {"current_id": "x", "seq": 1}) is False

        # marker without a next -> re-run (defensive).
        assert m._should_fast_forward({"seq": 1}, {"seq": 1}) is False


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
