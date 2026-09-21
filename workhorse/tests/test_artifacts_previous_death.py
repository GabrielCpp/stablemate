"""Tests for the previous-process detection at ``ArtifactWriter.resume``."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from workhorse.artifacts import ArtifactWriter, _process_alive
from workhorse.records import RunRecord, parse_run_record


def _record(run_dir: Path) -> RunRecord:
    return parse_run_record((run_dir / "run.json").read_text())


def _seed_dead_run(
    run_dir: Path, *, terminal: str | None = None, pid: int | None = None
) -> None:
    """Write a run.json shaped like one the previous attempt left behind."""
    run_dir.mkdir(parents=True, exist_ok=True)
    record = RunRecord(
        workflow="coder",
        run_id="pd",
        started_at="2026-09-01T00:00:00+00:00",
        terminal=terminal,
        pid=pid,
    )
    (run_dir / "run.json").write_text(record.model_dump_json(indent=2))


def test_process_alive_rejects_invalid_and_unknown_pids() -> None:
    """The probe must say False for pids the OS would reject too."""
    assert _process_alive(0) is False
    assert _process_alive(-1) is False
    assert _process_alive(2**31 - 1) is False
    assert _process_alive(2**31 - 1) is False


def test_process_alive_sees_this_test_runner() -> None:
    """Sanity check: the call returns True for a pid we know is alive."""
    assert _process_alive(os.getpid()) is True


def test_a_fresh_run_does_not_stamp_a_previous_process_death() -> None:
    """A fresh start has nothing to detect, so the new fields stay None."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        writer = ArtifactWriter("coder", runs, run_id="fresh")

        record = _record(writer.run_dir)
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_resume_of_a_run_with_an_alive_previous_pid_does_not_stamp() -> None:
    """The detection must read ``/proc`` — never the pid field alone."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        _seed_dead_run(run_dir, terminal=None, pid=os.getpid())
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        assert record.previous_process_died_at is None, (
            f"false alarm: pid {os.getpid()} is alive, "
            f"got stamp {record.previous_process_died_at!r}"
        )
        assert record.previous_process_pid is None


def test_resume_of_a_run_with_a_dead_previous_pid_stamps_the_record() -> None:
    """The load-bearing case the dashboard gap exposed: a segfaulted/SIGKILL'd run leaves a directory with ``terminal: null`` and a ``pid`` that the OS no longer knows about."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal=None, pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        before = time.time()
        resumed = ArtifactWriter.resume(run_dir)
        after = time.time()

        record = _record(resumed.run_dir)
        assert record.previous_process_pid == dead_pid, (
            f"expected the dead pid to be recorded for forensics; got {record.previous_process_pid}"
        )
        stamp = record.previous_process_died_at
        assert stamp is not None, "stamp must be set when the previous pid is gone"
        from datetime import datetime

        parsed = datetime.fromisoformat(stamp)
        assert before - 1 <= parsed.timestamp() <= after + 1


def test_resume_does_not_stamp_an_already_terminated_run() -> None:
    """A run that reached its terminal node wrote ``terminal``."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal="done", pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        assert record.terminal is None, "resume clears terminal when picking up"
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_the_previous_process_stamp_survives_subsequent_writes() -> None:
    """The stamp is sticky through the resumed run's own writes."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = runs / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal=None, pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)
        stamp_after_resume = _record(resumed.run_dir).previous_process_died_at

        resumed.write_state_checkpoint("investigate", {}, inputs={}, flow="Coder")

        record = _record(resumed.run_dir)
        assert record.previous_process_died_at == stamp_after_resume, (
            f"stamp must survive a state checkpoint; got {record.previous_process_died_at!r} "
            f"after writing (was {stamp_after_resume!r})"
        )
        assert record.previous_process_pid == dead_pid


def test_finish_clears_the_previous_process_stamp() -> None:
    """A finished run has its own end-state; the previous-process stamp is about the run's *history*, not its current state."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = runs / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal=None, pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)
        assert _record(resumed.run_dir).previous_process_died_at is not None

        resumed.finish(terminal="done")

        record = _record(resumed.run_dir)
        assert record.terminal == "done"
        assert record.previous_process_died_at is None, (
            "finish() must clear the previous-process stamp alongside the terminal marker"
        )
        assert record.previous_process_pid is None


def test_resume_without_run_json_does_not_stamp() -> None:
    """A run dir without ``run.json`` is a fresh dir the caller just opened; ``resume()`` falls through to an empty :class:`RunRecord`, whose ``pid`` is None, so the detection branch never fires."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        run_dir.mkdir(parents=True, exist_ok=True)
        assert not (run_dir / "run.json").exists()

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_resume_is_fail_soft_when_run_json_is_unparseable() -> None:
    """Best-effort, like every other read of this file."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("not json at all")
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        assert record.run_id == "coder-pd"
        assert record.previous_process_died_at is None, (
            "an unparseable record has pid=None; the detection branch never fires"
        )
        assert record.previous_process_pid is None


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
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
