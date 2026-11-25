"""`run_tool` with a time limit ends the tool and every child it started."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from workhorse_workflows.kit.tools import run_tool

PARENT = """import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
print(child.pid, flush=True)
time.sleep(60)
"""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[2] != "Z"
    except (ProcessLookupError, FileNotFoundError):
        return False


def test_a_tool_that_ends_in_time_returns_its_output() -> None:
    done = run_tool([sys.executable, "-c", "print('ok')"], timeout=30)

    assert (done.returncode, done.stdout) == (0, "ok\n")


def test_a_tool_past_its_limit_is_killed_with_the_child_it_started() -> None:
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        run_tool([sys.executable, "-c", PARENT], timeout=1)

    child = int(str(raised.value.stdout).split()[0])
    deadline = time.time() + 5
    while _alive(child) and time.time() < deadline:
        time.sleep(0.05)
    try:
        assert not _alive(child)
    finally:
        if _alive(child):
            os.kill(child, signal.SIGKILL)


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
def test_a_timed_tool_stays_in_the_callers_process_group() -> None:
    done = run_tool([sys.executable, "-c", "import os; print(os.getpgrp())"], timeout=30)

    assert int(done.stdout) == os.getpgrp()
