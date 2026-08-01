"""Tests for what a writer does with a run directory that is already occupied.

A run id derived from `--params` is deterministic (`workhorse.rundir`), so the same
command lands on the same directory every time. That is the point when the previous run
is resumable; when it finished, the next run starts *fresh in that same dir*, and what
happens to the bytes already there is this module's subject.

The answer used to be "delete the checkpoint and the event log" — the worst of the two
halves, since it destroys the record that an earlier run existed while keeping that
run's per-node evidence, now unlabelled. These tests pin the two directions that split:
a fresh start empties, a resume keeps.

Run: uv run python tests/test_artifacts_fresh.py   (or via pytest)
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import workhorse.artifacts as artifacts
from workhorse.artifacts import ArtifactWriter


def _leftovers(run_dir: Path, node_id: str = "flag_qa_failure") -> None:
    """Plant what a *previous* run in this directory would have left behind."""
    run_dir.mkdir(parents=True, exist_ok=True)
    node = run_dir / node_id
    node.mkdir(exist_ok=True)
    (node / "output.json").write_text('{"verdict": "from the previous run"}')
    (run_dir / ArtifactWriter.EVENTS_FILE).write_text('{"seq": 41, "node": "old"}\n')
    (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "old", "params": {}}')


def test_a_fresh_run_does_not_inherit_the_previous_runs_node_output():
    """A benchmark run showed this exactly: a re-run that passed every story and never
    entered `flag_qa_failure` or `flag_epic_blocked` shipped a run dir containing both
    nodes' output, left by the failed run before it — while its own 57 events mention
    neither. A post-mortem over that directory reports a clean run as having flagged a
    QA failure, and there is nothing on disk to catch the reading with."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _leftovers(runs / "coder-pdeadbeef")

        writer = ArtifactWriter("coder", runs, run_id="pdeadbeef")

        assert writer.run_dir == runs / "coder-pdeadbeef", writer.run_dir
        assert writer.read_output("flag_qa_failure") is None
        assert not (writer.run_dir / "flag_qa_failure").exists()
        assert not (writer.run_dir / ArtifactWriter.EVENTS_FILE).exists()
        assert writer.read_checkpoint() is None
        # The run it *is* still has to be recorded.
        assert (writer.run_dir / "run.json").exists()


def test_a_resume_keeps_everything_the_run_had_already_written():
    """The other half of the same rule. `pyflow.run._open_run` picks between these two
    constructors, and a resume that emptied the dir would throw away the work whose
    checkpoint it is resuming from."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pdeadbeef"
        _leftovers(run_dir)

        writer = ArtifactWriter.resume(run_dir)

        assert writer.read_output("flag_qa_failure") == {"verdict": "from the previous run"}
        assert (run_dir / ArtifactWriter.EVENTS_FILE).exists()


def test_re_entering_a_flow_scope_does_not_inherit_the_previous_visits_answers():
    """`at()` is the same fresh start one level down, and there it bites *within* a
    single run: a flow node in a loop re-enters one scope per iteration — the coder
    graph hands off to `Qa` once per story, always onto `<run>/qa/_flow`.

    That makes it a correctness hazard rather than only a reporting one, because
    `read_output` is a bare file-existence check whose contract is "None when it has not
    run". A state asking for a node this pass never reached would get the previous
    story's verdict and have no way to tell."""
    with tempfile.TemporaryDirectory() as tmp:
        parent = ArtifactWriter("coder", Path(tmp) / "runs", run_id="t")

        first = parent.subscope("qa", "Qa")
        first.write_step("assess", "prompt", {"verdict": "story one"}, {})
        assert first.read_output("assess") == {"verdict": "story one"}

        second = parent.subscope("qa", "Qa")

        assert second.run_dir == first.run_dir, "the loop re-enters the same scope"
        assert second.read_output("assess") is None


def test_a_genuine_mid_flow_resume_still_re_enters_in_place():
    """`subscope(resume=True)` is the engine's "we died inside this exact node" signal,
    and it must survive the emptying above — otherwise a resume replays every agent turn
    the sub-flow had already paid for."""
    with tempfile.TemporaryDirectory() as tmp:
        parent = ArtifactWriter("coder", Path(tmp) / "runs", run_id="t")
        scope = parent.subscope("qa", "Qa")
        scope.write_step("assess", "prompt", {"verdict": "story one"}, {})
        scope.write_state_checkpoint("assess", {}, inputs={}, flow="Qa")

        resumed = parent.subscope("qa", "Qa", resume=True)

        assert resumed.read_output("assess") == {"verdict": "story one"}
        assert resumed.read_checkpoint() is not None


def test_an_unremovable_run_dir_costs_the_wipe_but_not_the_run():
    """Housekeeping must never end a run that would otherwise work, so a tree that
    cannot be removed falls back to unlinking the two files that would actively corrupt
    this run: a stale checkpoint (which an auto-resume would resurrect if this run is
    interrupted before its own first checkpoint) and a stale event log (whose seq
    numbering restarts at 0 here, so the two runs' events would interleave)."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = runs / "coder-pdeadbeef"
        _leftovers(run_dir)

        def refuse(*args, **kwargs):
            raise OSError("device or resource busy")

        # `patch.object` rather than an assignment: `shutil.rmtree` is typed as a
        # protocol carrying `avoids_symlink_attacks`, so no plain function can be
        # assigned over it — and the patch puts the real one back on the way out.
        with patch.object(artifacts.shutil, "rmtree", refuse):
            writer = ArtifactWriter("coder", runs, run_id="pdeadbeef")

        assert writer.read_checkpoint() is None
        assert not (writer.run_dir / ArtifactWriter.EVENTS_FILE).exists()
        # The node dir is what could not be removed — the run continues regardless.
        assert (writer.run_dir / "flag_qa_failure").exists()


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
