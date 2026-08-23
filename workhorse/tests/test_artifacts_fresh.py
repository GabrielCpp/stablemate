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

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import workhorse.artifacts as artifacts
from workhorse import turnkey
from workhorse.artifacts import ArtifactWriter
from workhorse.records import parse_launch_record, parse_run_record


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


def _recorded(run_dir: Path):
    return parse_run_record((run_dir / "run.json").read_text())


def test_the_profile_and_what_it_held_are_recorded_on_the_run():
    """The name is what a resume re-applies; the tables are what answers "which model was
    at `high`" once the config file has moved on, which the name alone cannot."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("coder", Path(tmp) / "runs", run_id="t")
        assert _recorded(writer.run_dir).profile == ""

        writer.record_profile("cheap", {"power": {"high": {"claude": {"model": "sonnet"}}}})

        record = _recorded(writer.run_dir)
        assert record.profile == "cheap"
        assert record.profile_config["power"]["high"]["claude"]["model"] == "sonnet"


def test_a_resume_carries_the_recorded_profile_rather_than_clearing_it():
    """`resume()` rewrites run.json before the driver has said anything about a profile,
    so a carried-over value is the difference between a record and a file that forgets
    what the run is running on every time it picks back up."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-t"
        started = ArtifactWriter("coder", run_dir.parent, run_id="t")
        started.record_profile("cheap", {"default": {"claude": {"model": "haiku"}}})

        resumed = ArtifactWriter.resume(run_dir)

        record = _recorded(resumed.run_dir)
        assert record.profile == "cheap"
        assert record.profile_config == {"default": {"claude": {"model": "haiku"}}}
        # …and a run that finishes keeps it, rather than dropping it at the terminal.
        resumed.finish(terminal="done")
        assert _recorded(resumed.run_dir).profile == "cheap"


def _launched(run_dir: Path):
    return parse_launch_record((run_dir / "launch.json").read_text())


def test_the_run_dir_records_the_command_that_would_resume_it():
    """The record a watcher needs after the process it describes is gone. A SIGKILL'd run
    leaves a live checkpoint and a dead pid, and until this file the directory said
    everything about the run except how to start it again."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("coder", Path(tmp) / "runs", run_id="pdeadbeef")

        writer.record_launch(
            ["/venv/bin/python3", "/venv/bin/workhorse-coder", "run", "qa", "--no-cache"],
            ["/venv/bin/workhorse-coder", "run", "--resume-run", str(writer.run_dir)],
            "/work/acme",
        )

        record = _launched(writer.run_dir)
        assert record.cwd == "/work/acme"
        assert record.program == "/venv/bin/workhorse-coder"
        assert record.pid == os.getpid()
        # The whole reason the two argvs are separate fields: replaying the launch line
        # would delete the run directory this record exists to help someone save.
        assert "--no-cache" in record.argv
        assert "--no-cache" not in record.resume_argv
        assert record.resume_argv[-2:] == ["--resume-run", str(writer.run_dir)]


def test_a_resume_overwrites_the_launch_record_but_not_the_runs_own_start():
    """The two files answer different questions. `run.json` is about the run and carries
    its original start across resumes; `launch.json` is about one process, and the next
    process really was launched differently — a watcher that read a stale pid out of it
    would probe a pid that died two resumes ago and call the run healthy."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        writer = ArtifactWriter("coder", runs, run_id="pdeadbeef")
        writer.record_launch(["first"], ["first", "run"], "/work/acme")
        (writer.run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')
        (writer.run_dir / turnkey.GENERATION_FILE).write_text("2")
        started = _recorded(writer.run_dir).started_at

        resumed = ArtifactWriter.resume(writer.run_dir)
        resumed.record_launch(["second"], ["second", "run"], "/work/globex")

        assert _launched(resumed.run_dir).argv == ["second"]
        assert _launched(resumed.run_dir).cwd == "/work/globex"
        # …and it carries the generation, which is what any bounded auto-resume spends.
        assert _launched(resumed.run_dir).resume_generation == 2
        assert _recorded(resumed.run_dir).started_at == started


def test_a_nested_flow_scope_records_no_launch_of_its_own():
    """`at()`/`subscope()` open a writer for a flow scope inside a run — `<run>/qa/_flow`,
    once per story. A scope is not a process, so a launch record under one would be a
    claim that something started there, and a consumer walking run dirs would find
    several commands where there is one run."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("coder", Path(tmp) / "runs", run_id="pdeadbeef")
        writer.record_launch(["x"], ["x", "run"], "/work/acme")

        scope = writer.subscope("qa", "qa_flow")

        assert (writer.run_dir / "launch.json").exists()
        assert not (scope.run_dir / "launch.json").exists()


def test_an_unwritable_run_dir_does_not_take_the_run_down_with_it():
    """Best-effort, like every other record here. Keeping notes about a run must never be
    the thing that stops one."""
    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("coder", Path(tmp) / "runs", run_id="pdeadbeef")
        with patch.object(Path, "write_text", side_effect=OSError("read-only")):
            writer.record_launch(["x"], ["x", "run"], "/work/acme")
        assert not (writer.run_dir / "launch.json").exists()


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
