"""Tests for the two records a run writes to disk and reads back.

A checkpoint and an event line are not internal values that happen to be serialised:
they are what a relaunch at hour 30 has to make sense of, after a version change, a
kill mid-write, or an operator editing the file to unstick the run. So both directions
go through one model, and these are the tests that say what that model refuses.

The on-disk shapes are also a published surface — `events.jsonl` is joined against
provider spend by scorecards outside this repo — so the byte-level shape is asserted
here rather than left to whatever a serialiser felt like doing.

Run: uv run python tests/test_records.py   (or via pytest)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.errors import WorkflowFailed
from workhorse.records import NodeEvent, NodeGraphCheckpoint, PyflowCheckpoint, parse_checkpoint


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}")


def _writer(tmp) -> ArtifactWriter:
    return ArtifactWriter("research", Path(tmp), run_id="grammar-semantics")


# ------------------------------------------------------------------ the checkpoint


def test_the_checkpoint_written_is_the_checkpoint_read():
    """The round trip, whole: what the engine writes comes back as the same values,
    off disk, with no caller pulling keys out by hand."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint(
            "qa_gate",
            {"story": "login", "attempt": 2},
            inputs={"repo": "acme/api-service"},
            flow="Coder",
            ctx={"branch": "main"},
            waiting_on="docs/approval.md",
        )
        cp = w.read_checkpoint()
        assert isinstance(cp, PyflowCheckpoint), cp
        assert cp.state == "qa_gate"
        assert cp.params == {"story": "login", "attempt": 2}
        assert cp.inputs == {"repo": "acme/api-service"}
        assert cp.flow == "Coder" and cp.ctx == {"branch": "main"}
        assert cp.waiting_on == "docs/approval.md"
        assert cp.workflow == "research" and cp.run_id == "grammar-semantics"
        assert cp.seq == 1


def test_the_engine_field_is_a_discriminator_not_a_comment():
    """The two engines shared a runs directory, so a checkpoint has to say which one
    wrote it — and reading the wrong one must fail by name rather than by coincidence."""
    node_graph = parse_checkpoint(json.dumps({"current_id": "plan", "context": {"x": 1}}))
    assert isinstance(node_graph, NodeGraphCheckpoint), node_graph

    exc = _raises(WorkflowFailed, read_resume, node_graph)
    assert "YAML engine" in str(exc) and "plan" in str(exc), exc


def test_a_checkpoint_that_is_neither_engines_is_refused():
    """`state` is what a resume calls. A checkpoint missing it is not a checkpoint to
    fall back through — it is one to say so about, on the way off disk."""
    exc = _raises(ValidationError, parse_checkpoint, json.dumps({"engine": "pyflow"}))
    assert "state" in str(exc), exc
    _raises(ValidationError, parse_checkpoint, json.dumps({"engine": "pyflow", "state": ""}))
    _raises(ValidationError, parse_checkpoint, "{not json")


def test_the_annotations_are_optional_because_an_operator_edits_this_file():
    """The three provenance fields nothing reads back carry defaults on purpose: a
    hand-trimmed checkpoint at hour 30 must still resume."""
    cp = parse_checkpoint(json.dumps({"engine": "pyflow", "state": "implement"}))
    resume = read_resume(cp)
    assert resume.state == "implement" and resume.params == {} and resume.inputs == {}


def test_resume_reads_the_seq_back_off_the_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("a", {}, inputs={})
        w.write_state_checkpoint("b", {}, inputs={})
        assert ArtifactWriter.resume(w.run_dir)._seq == 2


def test_checkpoint_write_returns_the_sequence_it_committed():
    """The driver keys an execution span to the checkpoint it is about to dispatch.
    Returning the committed sequence prevents it from guessing at writer internals."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        assert w.write_state_checkpoint("a", {}, inputs={}) == 1
        assert w.write_state_checkpoint("b", {}, inputs={}) == 2
        resumed = ArtifactWriter.resume(w.run_dir)
        assert resumed.write_state_checkpoint("c", {}, inputs={}) == 3


def test_an_unreadable_checkpoint_costs_the_seq_and_nothing_else():
    """Resuming is the failure path's own path; a corrupt checkpoint there must not
    raise on top of whatever sent us here."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.write_state_checkpoint("a", {}, inputs={})
        (w.run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text("{half-writ")
        assert ArtifactWriter.resume(w.run_dir)._seq == 0


# ------------------------------------------------------------------- the event log


def test_event_extras_stay_top_level_on_disk():
    """External scorecards read these lines. `next`/`waiting_on`/the per-node-kind
    context are top-level keys today and stay top-level keys — a record that nested
    them under `extra` would be a format change wearing a refactor's clothes."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.record_node("implement", "enter", blueprint="coder", model="a-model")
        w.write_step("implement", "p", {}, {}, next_node="qa_gate")
        lines = [json.loads(x) for x in (w.run_dir / "events.jsonl").read_text().splitlines()]
        assert list(lines[0]) == ["ts", "seq", "node", "phase", "blueprint", "model"]
        assert lines[0]["blueprint"] == "coder" and lines[0]["model"] == "a-model"
        assert lines[1] == {
            "ts": lines[1]["ts"],
            "seq": 0,
            "node": "implement",
            "phase": "done",
            "next": "qa_gate",
        }


def test_the_phase_set_is_closed():
    """Every consumer switches on `phase`; a fifth value nobody handles would be a
    silent no-op at the far end of the join."""
    _raises(ValidationError, NodeEvent, ts="now", seq=1, node="a", phase="finished")
    assert NodeEvent(ts="now", seq=1, node="a", phase="terminal").phase == "terminal"


def test_read_events_skips_a_line_it_cannot_parse():
    """An append-only log a kill can truncate mid-line: reading instrumentation must
    not be the thing that fails."""
    with tempfile.TemporaryDirectory() as tmp:
        w = _writer(tmp)
        w.record_node("a", "enter")
        with (w.run_dir / "events.jsonl").open("a") as f:
            f.write('{"ts": "now", "seq": 1, "node": "b", "ph\n')
        w.record_node("a", "done", next="c")
        assert [(e.node, e.phase) for e in w.read_events()] == [("a", "enter"), ("a", "done")]


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
