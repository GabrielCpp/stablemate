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
