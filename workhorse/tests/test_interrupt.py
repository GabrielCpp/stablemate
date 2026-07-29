"""Tests for recording an operator interrupt (Ctrl-C) as an error.

A SIGINT used to leave no trace of itself: the in-flight node's `enter` event never
got its `done`, and run.json looked exactly like a run still sitting in that node —
so a stopped run and a wedged one were indistinguishable without going to the backend
CLI's session transcript. These pin the stamp, and pin that it does NOT mark the run
finished (which would break auto-resume-in-place).

Run: ./.venv/bin/python tests/test_interrupt.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path

from workhorse.artifacts import ArtifactWriter

m = importlib.import_module("workhorse.main")


def _writer(tmp):
    return ArtifactWriter("author", Path(tmp), run_id="rerun1")


def _run_json(w):
    return json.loads((w.run_dir / "run.json").read_text())


def test_interrupt_appends_error_event_for_the_inflight_node():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("split_stories", {})
        w.record_interrupt("split_stories", "KeyboardInterrupt")
        events = w.read_events()
        assert [e["phase"] for e in events] == ["enter", "error"]
        assert events[-1]["node"] == "split_stories"
        assert events[-1]["error"] == "KeyboardInterrupt"
        assert events[-1]["seq"] == events[0]["seq"]


def test_interrupt_stamps_run_json_without_finishing_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("split_stories", {})
        w.record_interrupt("split_stories", "KeyboardInterrupt")
        meta = _run_json(w)
        # Stopped, but NOT over: a non-null terminal would make _auto_resolve treat
        # this dir as finished and start a fresh run instead of resuming it.
        assert meta["terminal"] is None
        assert meta["ended_at"] is None
        assert meta["error"] == "KeyboardInterrupt"
        assert meta["interrupted_at"] is not None


def test_interrupted_run_is_still_auto_resumable():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("split_stories", {})
        w.record_interrupt("split_stories", "KeyboardInterrupt")
        _run_id, resume_dir = m._auto_resolve(Path(tmp), "author", "rerun1")
        assert resume_dir == w.run_dir


def test_resume_clears_the_interrupt_stamp():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("split_stories", {})
        w.record_interrupt("split_stories", "KeyboardInterrupt")
        w2 = ArtifactWriter.resume(w.run_dir)
        meta = _run_json(w2)
        assert meta["interrupted_at"] is None and meta["error"] is None


def test_finish_leaves_no_interrupt_stamp():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("done", {})
        w.finish(terminal="terminal")
        meta = _run_json(w)
        assert meta["terminal"] == "terminal" and meta["ended_at"] is not None
        assert meta["interrupted_at"] is None and meta["error"] is None


def test_record_interrupt_helper_reads_the_node_from_the_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_checkpoint("audit_story", {})
        m._record_interrupt(w)
        event = w.read_events()[-1]
        assert event["node"] == "audit_story"
        assert event["phase"] == "error"
        assert event["error"] == "KeyboardInterrupt"


def test_record_interrupt_helper_survives_a_missing_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        m._record_interrupt(w)  # no checkpoint written yet — must not raise
        assert w.read_events()[-1]["node"] == "<run>"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
