"""The reaper: a round does not get to leave its processes holding ports.

The bug these cover is a sibling-round collision — an earlier round's server still
answering on the port the next round asks for, which looks like the new build working.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from paddock import reap


def _sleeper(cwd: Path, *, trap: bool = False) -> subprocess.Popen[bytes]:
    """A process standing in `cwd` and nothing else. `trap` makes it ignore SIGTERM."""
    code = (
        "import signal, time\n"
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if trap else "")
        + "time.sleep(300)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=str(cwd))
    # The child's cwd is only readable once it has actually started.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if Path(f"/proc/{proc.pid}/cwd").resolve() == cwd.resolve():
                return proc
        except OSError:
            pass
        time.sleep(0.05)
    proc.kill()
    pytest.fail("the helper process never reported its working directory")


def _reaped(proc: subprocess.Popen[bytes]) -> bool:
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return False
    return True


def test_reaps_a_process_standing_in_the_stage(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    proc = _sleeper(stage)
    try:
        left = reap.reap(stage)
        assert [s.pid for s in left] == [proc.pid]
        assert _reaped(proc), "the reaper reported it but the process is still running"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_reaps_a_process_in_a_subdirectory_of_the_stage(tmp_path: Path) -> None:
    """The leak that bit us was a server built and run inside the unpacked repo."""
    deep = tmp_path / "stage" / "link-shortener" / "cmd"
    deep.mkdir(parents=True)
    proc = _sleeper(deep)
    try:
        assert [s.pid for s in reap.reap(tmp_path / "stage")] == [proc.pid]
        assert _reaped(proc)
    finally:
        if proc.poll() is None:
            proc.kill()


def test_leaves_a_process_outside_the_stage_alone(tmp_path: Path) -> None:
    """A sibling round's stage, and the user's own shell, are not this round's to kill."""
    stage = tmp_path / "stage"
    stage.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    proc = _sleeper(other)
    try:
        assert reap.reap(stage) == []
        assert proc.poll() is None, "the reaper killed a process outside the stage"
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_a_sibling_prefix_is_not_inside_the_stage(tmp_path: Path) -> None:
    """`.../stage2` starts with `.../stage` as a string but is a different directory."""
    stage = tmp_path / "stage"
    stage.mkdir()
    sibling = tmp_path / "stage2"
    sibling.mkdir()
    proc = _sleeper(sibling)
    try:
        assert reap.reap(stage) == []
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_kills_what_ignores_sigterm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(reap, "GRACE_SECONDS", 0.5)
    proc = _sleeper(stage, trap=True)
    try:
        assert [s.pid for s in reap.reap(stage)] == [proc.pid]
        assert _reaped(proc), "a SIGTERM-ignoring process survived the reaper"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_never_reaps_its_own_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """paddock running from inside a stage must not send itself SIGTERM."""
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.chdir(stage)
    assert os.getpid() not in [s.pid for s in reap.survivors(stage)]


def test_excludes_the_pids_the_caller_names(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    proc = _sleeper(stage)
    try:
        assert reap.survivors(stage, exclude=frozenset({proc.pid})) == []
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)


def test_reports_the_command_line_so_the_leak_is_diagnosable(tmp_path: Path) -> None:
    """The reaper is the net, not the fix — what leaked has to be readable in the log."""
    stage = tmp_path / "stage"
    stage.mkdir()
    proc = _sleeper(stage)
    try:
        [survivor] = reap.survivors(stage)
        assert "time.sleep(300)" in survivor.cmdline
        assert str(proc.pid) in str(survivor)
    finally:
        proc.kill()
        proc.wait(timeout=10)
