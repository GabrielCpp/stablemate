"""Tests for the shared supervised spawn path (agent.stream_subprocess).

These cover the hardening that lets a single wedged turn NOT freeze an unattended
run: the out-of-band watchdog force-kills the whole process group even when the
reader is blocked mid-readline on a stream that stalled after a partial line — the
exact failure that previously hung a QA node for ~12h. Runnable two ways:
    ./.venv/bin/python -m pytest tests/test_stream_subprocess.py
"""
from __future__ import annotations

import os
import sys
import time

from workhorse.runner import agent


def _run(code: str, *, timeout: float, grace: float = 1.0):
    """Run a tiny python program as the 'agent', collecting streamed lines."""
    lines: list[str] = []
    orig_grace = agent._WATCHDOG_GRACE_S
    agent._WATCHDOG_GRACE_S = grace
    try:
        timed_out, rc = agent.stream_subprocess(
            [sys.executable, "-u", "-c", code],
            "test_node",
            timeout,
            lines.append,
        )
    finally:
        agent._WATCHDOG_GRACE_S = orig_grace
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
    beats: list[tuple[str, float, float]] = []
    orig_every, orig_beat = agent._HEARTBEAT_EVERY_S, agent.otel.turn_heartbeat
    agent._HEARTBEAT_EVERY_S = 0.1
    agent.otel.turn_heartbeat = lambda node, idle, elapsed: beats.append((node, idle, elapsed))
    try:
        # Writes one line, then goes silent until the turn's deadline.
        agent.stream_subprocess(
            [sys.executable, "-u", "-c",
             "import sys, time; print('hello'); sys.stdout.flush(); time.sleep(3600)"],
            "select_item",
            3.0,
            lambda _line: None,
        )
    finally:
        agent._HEARTBEAT_EVERY_S = orig_every
        agent.otel.turn_heartbeat = orig_beat

    assert beats, "a silent turn emitted no heartbeat — a stall would be invisible"
    assert all(node == "select_item" for node, _, _ in beats)
    # idle_s must GROW while the stream is quiet: that is what distinguishes a
    # wedged turn from a healthy streaming one.
    idles = [idle for _, idle, _ in beats]
    assert idles[-1] > idles[0], f"idle_s did not climb during silence: {idles}"


def test_heartbeat_idle_resets_when_the_stream_speaks():
    """A chatty turn must keep idle_s near zero however long it runs — otherwise a
    healthy long turn would look identical to a hang."""
    beats: list[float] = []
    orig_every, orig_beat = agent._HEARTBEAT_EVERY_S, agent.otel.turn_heartbeat
    agent._HEARTBEAT_EVERY_S = 0.1
    agent.otel.turn_heartbeat = lambda _n, idle, _e: beats.append(idle)
    try:
        agent.stream_subprocess(
            [sys.executable, "-u", "-c",
             "import sys, time\n"
             "for _ in range(20):\n"
             "    print('tok'); sys.stdout.flush(); time.sleep(0.05)\n"],
            "investigate",
            30.0,
            lambda _line: None,
        )
    finally:
        agent._HEARTBEAT_EVERY_S = orig_every
        agent.otel.turn_heartbeat = orig_beat

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


if __name__ == "__main__":
    test_clean_stream_completes_without_timeout()
    test_wedged_midline_is_killed_by_watchdog()
    test_group_children_are_reaped()
    print("ok")
