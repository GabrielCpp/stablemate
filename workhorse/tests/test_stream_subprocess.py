"""Tests for the shared supervised spawn path (process.stream_subprocess).

These cover the hardening that lets a single wedged turn NOT freeze an unattended
run: the out-of-band watchdog force-kills the whole process group even when the
reader is blocked mid-readline on a stream that stalled after a partial line — the
exact failure that previously hung a QA node for ~12h. Runnable two ways:
    ./.venv/bin/python -m pytest tests/test_stream_subprocess.py
"""
from __future__ import annotations

import os
import sys
import threading
import time

from _fakes import RecordingTelemetry
from workhorse import control, otel, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import process


def _run(code: str, *, timeout: float, grace: float = 1.0):
    """Run a tiny python program as the 'agent', collecting streamed lines."""
    lines: list[str] = []
    timed_out, rc = process.stream_subprocess(
        [sys.executable, "-u", "-c", code],
        "test_node",
        timeout,
        lines.append,
        resilience=AgentResilience(watchdog_grace_s=grace),
    )
    return timed_out, rc, lines


def test_clean_stream_completes_without_timeout():
    timed_out, rc, lines = _run(
        "import sys; sys.stdout.write('a\\nb\\n'); sys.stdout.flush()",
        timeout=30,
    )
    assert timed_out is False
    assert rc == 0
    assert [ln.strip() for ln in lines] == ["a", "b"]


def test_silent_stream_still_emits_liveness_heartbeats():
    """The wedged case: a turn producing NO output must still report that it is
    alive and how long it has been quiet. Its span cannot say so — an unfinished
    span never exports — so the heartbeat is the only signal, and it has to come
    from the top of the select loop rather than from a per-line hook.

    Note the 3s budget: select blocks in ~1s slices, so the beat check only runs
    as each slice returns. Heartbeat granularity is therefore ~1s at best, which
    is irrelevant at the 10s production default but bounds this test.
    """
    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        # Writes one line, then goes silent until the turn's deadline.
        process.stream_subprocess(
            [sys.executable, "-u", "-c",
             "import sys, time; print('hello'); sys.stdout.flush(); time.sleep(3600)"],
            "select_item",
            3.0,
            lambda _line: None,
            resilience=AgentResilience(heartbeat_every_s=0.1),
        )
    finally:
        otel.install(previous)

    beats = fake.beats
    assert beats, "a silent turn emitted no heartbeat — a stall would be invisible"
    assert all(node == "select_item" for node, _, _ in beats)
    # idle_s must GROW while the stream is quiet: that is what distinguishes a
    # wedged turn from a healthy streaming one.
    idles = [idle for _, idle, _ in beats]
    assert idles[-1] > idles[0], f"idle_s did not climb during silence: {idles}"


def test_heartbeat_idle_resets_when_the_stream_speaks():
    """A chatty turn must keep idle_s near zero however long it runs — otherwise a
    healthy long turn would look identical to a hang."""
    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        process.stream_subprocess(
            [sys.executable, "-u", "-c",
             "import sys, time\n"
             "for _ in range(20):\n"
             "    print('tok'); sys.stdout.flush(); time.sleep(0.05)\n"],
            "investigate",
            30.0,
            lambda _line: None,
            resilience=AgentResilience(heartbeat_every_s=0.1),
        )
    finally:
        otel.install(previous)

    beats = [idle for _node, idle, _elapsed in fake.beats]
    assert beats, "a streaming turn emitted no heartbeat"
    assert max(beats) < 0.5, f"idle_s climbed on a streaming turn: {beats}"


def test_wedged_midline_is_killed_by_watchdog():
    """A process that writes a partial line (no newline) then sleeps forever must be
    force-killed within timeout+grace — before this fix, readline() blocked and the
    in-loop wall-clock check never ran again, hanging the node indefinitely."""
    start = time.monotonic()
    timed_out, rc, _ = _run(
        "import sys, time; sys.stdout.write('partial-no-newline'); "
        "sys.stdout.flush(); time.sleep(3600)",
        timeout=1,
        grace=1,
    )
    elapsed = time.monotonic() - start
    assert timed_out is True
    assert rc != 0  # SIGKILLed
    # timeout(1) + grace(1) + reap slack — must NOT run anywhere near the 3600s sleep.
    assert elapsed < 20, f"watchdog did not fire promptly (took {elapsed:.1f}s)"


class _SteppingClock:
    """A clock whose ``monotonic`` jumps a fixed step every time it is read.

    Not a ``FakeClock``: nothing in the stream loop sleeps, so a clock that only moves
    on ``sleep`` would never reach any deadline. Time here advances because it was
    *observed*, which is enough to drive a wall-clock check and nothing else.
    """

    def __init__(self, step: float) -> None:
        self.step = step
        self.t = 0.0

    def now(self):
        raise AssertionError("the stream loop must not ask for wall-clock time")

    def monotonic(self) -> float:
        self.t += self.step
        return self.t - self.step

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_the_turn_deadline_is_measured_on_the_injected_clock():
    """A two-hour timeout expires in about a second, because the supervisor is handed
    its clock rather than importing one.

    This is the seam the module-level ``_active``/``time.monotonic()`` pair could not
    offer: the production default is still the real clock, but a test that wants to see
    an overrun turn get killed no longer has to wait out the overrun.
    """
    clock = _SteppingClock(step=3600.0)
    supervisor = process.ProcessSupervisor(clock=clock)
    start = time.monotonic()
    timed_out, rc = supervisor.stream(
        [sys.executable, "-u", "-c", "import time; time.sleep(3600)"],
        "slow_node",
        7200.0,                      # two hours, on the fake clock
        lambda _line: None,
        resilience=AgentResilience(watchdog_grace_s=3600),  # never fires; the loop wins
    )
    elapsed = time.monotonic() - start
    assert timed_out is True
    assert rc != 0                   # the overrunning turn's group was killed
    assert elapsed < 20, f"a fake two-hour deadline took {elapsed:.1f}s of real time"


def test_group_children_are_reaped():
    """The agent's grandchildren (e.g. MCP servers / browsers) must die with the group
    when a turn is force-killed, not orphan. We spawn a child that writes its PID, then
    both parent and child sleep; after the watchdog fires, the child must be gone."""
    code = (
        "import os, sys, subprocess, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3600)'])\n"
        "sys.stdout.write(str(child.pid))\n"  # partial line → wedge the reader
        "sys.stdout.flush()\n"
        "time.sleep(3600)\n"
    )
    _timed_out, _rc, lines = _run(code, timeout=1, grace=1)
    child_pid = int("".join(lines).strip())
    # Give the SIGKILL a moment to propagate to the group.
    deadline = time.monotonic() + 5
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            alive = False
            break
    assert alive is False, f"grandchild {child_pid} survived the group kill (orphan)"


def test_the_child_pwd_matches_the_cwd_it_was_spawned_in(tmp_path):
    """A CLI that resolves its project root from ``$PWD`` (OpenCode does) must land in
    the node's repo, not the one workhorse was launched from.

    ``Popen(cwd=…)`` alone leaves the inherited ``PWD`` behind, and the benchmark
    harness launches every phase from the stablemate checkout — so every agent turn
    read and wrote stablemate instead of the target repo.
    """
    target = tmp_path / "target-repo"
    target.mkdir()
    lines: list[str] = []
    process.stream_subprocess(
        [sys.executable, "-u", "-c", "import os; print(os.environ['PWD'])"],
        "test_node",
        30,
        lines.append,
        resilience=AgentResilience(),
        cwd=str(target),
    )
    assert "".join(lines).strip() == str(target.resolve())


def test_the_stale_oldpwd_is_dropped_when_the_child_moves(tmp_path):
    """``cd -`` in an agent's shell must not jump to the launcher's directory: the
    child never performed the ``cd`` that ``OLDPWD`` describes."""
    target = tmp_path / "target-repo"
    target.mkdir()
    os.environ["OLDPWD"] = str(tmp_path / "somewhere-else")
    lines: list[str] = []
    try:
        process.stream_subprocess(
            [sys.executable, "-u", "-c", "import os; print(os.environ.get('OLDPWD', '<unset>'))"],
            "test_node",
            30,
            lines.append,
            resilience=AgentResilience(),
            cwd=str(target),
        )
    finally:
        os.environ.pop("OLDPWD", None)
    assert "".join(lines).strip() == "<unset>"


def test_a_reload_request_cuts_the_streaming_turn_within_a_slice(tmp_path):
    """The property the whole feature's value rests on: latency, not eventual delivery.

    The 'agent' here would run for an hour. An operator plants a request while it streams,
    and the turn has to end in about the length of one select slice — the saving is exactly
    the tokens the turn would have burned after that instant.

    A real socket and a real client, so this covers the listening fd joining the stream's
    own select and not merely the policy sitting above it.
    """
    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    channel = control.SocketChannel.open(tmp_path)
    control.arm(channel)
    sender = threading.Thread(
        target=lambda: control.send(tmp_path, control.Request(), timeout=20)
    )
    sender.start()
    try:
        started = time.monotonic()
        raised = None
        try:
            process.stream_subprocess(
                [sys.executable, "-u", "-c",
                 "import sys, time; print('working'); sys.stdout.flush(); time.sleep(3600)"],
                "test_node",
                3600,
                lambda line: None,
                resilience=AgentResilience(),
            )
        except reload.ReloadRequested as exc:
            raised = exc
        elapsed = time.monotonic() - started
    finally:
        sender.join(timeout=20)
        control.arm(None)
        channel.close()
        otel.install(previous)

    assert raised is not None, "the stream must report the reload, not a verdict on the turn"
    assert raised.core is False
    assert elapsed < 10, elapsed
    # Recorded BEFORE the kill, so the turn's span closes with the usage it really accrued.
    names = [name for name, _, _ in fake.events]
    assert "reload_kill" in names
    name, error, attrs = next(event for event in fake.events if event[0] == "reload_kill")
    assert error is False, "a reload is not an error; groom must not read it as one"
    assert attrs["node"] == "test_node"


def test_an_at_boundary_request_does_not_touch_the_streaming_turn(tmp_path):
    """`--at-boundary` is the case for a turn 95% through work that is not broken.

    Scripted rather than socketed: the policy is what is under test here, and the stream
    loop asks the channel on every slice whether or not there was an fd to select on.
    """
    fake = RecordingTelemetry()
    previous = otel.install(otel.TelemetryHost(active=fake))
    channel = control.FakeChannel(control.Request(at_boundary=True))
    control.arm(channel)
    try:
        timed_out, rc, lines = _run(
            "import sys; sys.stdout.write('a\\n'); sys.stdout.flush()", timeout=30
        )
        # Declined by the stream loop, acknowledged, and kept for the state boundary —
        # taking it off a socket consumes it, so declining has to mean remembering it.
        assert channel.replies == [{"ok": True, "cut": False}]
        assert reload.boundary_requested() is not None
    finally:
        control.arm(None)
        otel.install(previous)

    assert timed_out is False and rc == 0
    assert [ln.strip() for ln in lines] == ["a"]
    assert [name for name, _, _ in fake.events if name == "reload_kill"] == []


def test_an_unarmed_process_never_sees_a_request():
    """Nothing listens until a run arms one — every other test streams with it inert."""
    control.arm(None)
    assert control.armed().fileno() is None
    timed_out, rc, _ = _run("import sys; sys.stdout.write('a\\n')", timeout=30)
    assert timed_out is False and rc == 0


if __name__ == "__main__":
    test_clean_stream_completes_without_timeout()
    test_the_turn_deadline_is_measured_on_the_injected_clock()
    test_wedged_midline_is_killed_by_watchdog()
    test_group_children_are_reaped()
    print("ok")
