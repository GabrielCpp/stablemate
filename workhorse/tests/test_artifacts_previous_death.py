"""Tests for the previous-process detection at ``ArtifactWriter.resume``.

A SIGKILL, segfault, OOM-kill or host power loss takes the engine down without
writing ``run.json``'s terminal marker, so the directory the next resume picks
up says ``terminal: null`` AND ``pid: <the one that is gone>``. Without a
second signal groom reads that as "still in flight", and the run drifts off
the dashboard for as long as no one opens the directory.

The detection lives here: when ``resume()`` reads a record whose ``terminal``
is unset and whose ``pid`` is no longer a running process, it stamps the
record with ``previous_process_died_at`` and ``previous_process_pid`` before
the new run's first checkpoint can clobber the story.

Run: ``uv run python tests/test_artifacts_previous_death.py`` (or via pytest).
"""

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
    """Write a run.json shaped like one the previous attempt left behind.

    ``pid=None`` simulates a record that was never stamped with one (e.g., the
    very first write of an old-format dir), so the resume side does not even
    try to look it up.
    """
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
    """The probe must say False for pids the OS would reject too.

    Bounds check matches what a kill syscall would do: a pid of 0, -1 or
    anything outside the kernel's pid_t range is not a process. Negative
    numbers come up in test rigs (sentinels, defaults) and a False here is
    what keeps us from stamping a death we cannot confirm."""
    assert _process_alive(0) is False
    assert _process_alive(-1) is False
    assert _process_alive(2**31 - 1) is False
    # The kernel's pid_t max on Linux is 2**22 by default; pick something above
    # that — well past any /proc entry, well past any recyclable pid.
    assert _process_alive(2**31 - 1) is False


def test_process_alive_sees_this_test_runner() -> None:
    """Sanity check: the call returns True for a pid we know is alive."""
    assert _process_alive(os.getpid()) is True


def test_a_fresh_run_does_not_stamp_a_previous_process_death() -> None:
    """A fresh start has nothing to detect, so the new fields stay None.

    Without this, a regression that defaults the new fields to a non-None
    value would falsely flag every fresh run as having resumed a dead one."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        writer = ArtifactWriter("coder", runs, run_id="fresh")

        record = _record(writer.run_dir)
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_resume_of_a_run_with_an_alive_previous_pid_does_not_stamp() -> None:
    """The detection must read ``/proc`` — never the pid field alone.

    Recording a stamp for an alive pid would be the false alarm: another
    process really *is* running this run dir (a peer supervisor, a manual
    ``workhorse-coder run`` in another terminal), and the resumed run
    would surface a "previous died" event that never happened."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        # The test runner itself is alive (we just confirmed above). Plant the
        # run.json as if a previous attempt of *this* pid were still going.
        # _process_alive(pid) must say True, so resume() must not stamp.
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
    """The load-bearing case the dashboard gap exposed: a segfaulted/SIGKILL'd
    run leaves a directory with ``terminal: null`` and a ``pid`` that the OS
    no longer knows about. The next resume must surface that fact.

    Without this stamp groom treats the run as in-flight until telemetry
    ages out (it never does for crashed runs — the spans stop exporting on
    the node that was in flight when the interpreter fell, so no signal ever
    tells groom the run is dead). The stamp is the second signal: what is
    on disk says what telemetry cannot.
    """
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        dead_pid = 2**31 - 1  # outside kernel pid_t; never alive
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
        # ISO-8601 round-trip — the stamp is what groom reads, and a string
        # timestamp that fails to parse buys nothing on the other side.
        from datetime import datetime

        parsed = datetime.fromisoformat(stamp)
        # …and the stamp falls in the window between the test entering resume()
        # and exiting it, confirming the writer actually wrote *now* (not a
        # carried-over value from a stale record).
        assert before - 1 <= parsed.timestamp() <= after + 1


def test_resume_does_not_stamp_an_already_terminated_run() -> None:
    """A run that reached its terminal node wrote ``terminal``. The
    detection must not stamp those — they finished cleanly, and a
    ``previous_process_died_at`` on a successfully finished run would
    misread to groom as "still going, but the last attempt died".

    Resume is short-circuited elsewhere for terminal runs (see
    :mod:`workhorse.rundir`), but the stamp path itself has to be a
    no-op here so a direct artifact-layer resume test does not read
    wrong.
    """
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal="done", pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        # Resume cleared terminal to None (it's an in-progress run *now*)
        # but the previous-process stamp is for previous-process death, and
        # there was no previous-process death — the run finished normally.
        assert record.terminal is None, "resume clears terminal when picking up"
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_the_previous_process_stamp_survives_subsequent_writes() -> None:
    """The stamp is sticky through the resumed run's own writes.

    Every write of ``run.json`` goes through ``_write_run_json``, which
    also stamps ``interrupted_at`` (operator Ctrl-C) and clears the
    profile's ``ended_at``. A previous-process stamp wiped on each
    checkpoint would defeat the dashboard gap, which only matters while
    the run is in flight. The pattern is the same one ``operator_interrupted``
    uses, only the field is different: ``interrupted_at`` is recomputed
    on every call, ``previous_process_died_at`` is held on the writer
    and threaded in until ``finish()`` clears both.
    """
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = runs / "coder-pd"
        dead_pid = 2**31 - 1
        _seed_dead_run(run_dir, terminal=None, pid=dead_pid)
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        resumed = ArtifactWriter.resume(run_dir)
        stamp_after_resume = _record(resumed.run_dir).previous_process_died_at

        # Drive a state checkpoint through — this is the path the driver
        # walks on every node visit, and the one any "clear on write"
        # regression would surface through.
        resumed.write_state_checkpoint("investigate", {}, inputs={}, flow="Coder")

        record = _record(resumed.run_dir)
        assert record.previous_process_died_at == stamp_after_resume, (
            f"stamp must survive a state checkpoint; got {record.previous_process_died_at!r} "
            f"after writing (was {stamp_after_resume!r})"
        )
        assert record.previous_process_pid == dead_pid


def test_finish_clears_the_previous_process_stamp() -> None:
    """A finished run has its own end-state; the previous-process stamp is
    about the run's *history*, not its current state. Keeping it on a
    finished run misreads to groom ("process died mid-flight and then
    finished, somehow?") and confuses a post-mortem.

    The seam: ``finish()`` writes the terminal marker and is the only call
    site that legitimately knows the run is over. Clearing the writer's
    two new fields before that write is what makes the next read tell the
    truth.
    """
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
    """A run dir without ``run.json`` is a fresh dir the caller just
    opened; ``resume()`` falls through to an empty :class:`RunRecord`,
    whose ``pid`` is None, so the detection branch never fires.

    Without this, an empty dir would be misstamped on its first resume."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        run_dir.mkdir(parents=True, exist_ok=True)
        # No run.json, no checkpoint — exactly the state _clear_stale_run
        # leaves behind for the resumable-but-unmarked path.
        assert not (run_dir / "run.json").exists()

        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        assert record.previous_process_died_at is None
        assert record.previous_process_pid is None


def test_resume_is_fail_soft_when_run_json_is_unparseable() -> None:
    """Best-effort, like every other read of this file. A run dir whose
    ``run.json`` is corrupted (operator edit, half-written previous crash)
    must not raise — the engine writes a fresh record and starts over.

    The detection in :func:`ArtifactWriter.resume` is the same code path:
    a ``ValidationError`` becomes an empty record, which has ``pid = None``
    and so no stamp. This test pins that contract."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "coder-pd"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("not json at all")
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text('{"state": "s"}')

        # The fail-soft contract: the call returns; no exception leaks out.
        resumed = ArtifactWriter.resume(run_dir)

        record = _record(resumed.run_dir)
        # …and resume wrote a fresh record, with workflow/run_id defaulted to
        # the dir name (the same convention every other unparseable-record
        # fallback uses). That is what makes the dir usable again.
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
