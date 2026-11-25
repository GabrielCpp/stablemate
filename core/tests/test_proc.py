from __future__ import annotations

import os
import subprocess
import sys

import pytest

from stablemate_core import proc


def test_a_non_positive_pid_is_neither_alive_nor_started() -> None:
    assert not proc.pid_alive(0)
    assert not proc.pid_alive(-3)
    assert proc.pid_start_token(0) == ""
    assert proc.pid_start_token(-3) == ""


def test_this_process_is_alive_with_a_stable_start_token() -> None:
    token = proc.pid_start_token(os.getpid())
    assert proc.pid_alive(os.getpid())
    assert token
    assert proc.pid_start_token(os.getpid()) == token


def test_a_finished_child_is_neither_alive_nor_started() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not proc.pid_alive(child.pid)
    assert proc.pid_start_token(child.pid) == ""


@pytest.mark.skipif(not hasattr(os, "waitid"), reason="waitid is POSIX only")
def test_a_zombie_child_is_not_alive() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        while proc.pid_alive(child.pid):
            os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
        assert not proc.pid_alive(child.pid)
    finally:
        child.wait()


@pytest.mark.parametrize("platform", ["darwin", "freebsd14"])
def test_the_ps_path_answers_without_proc(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    monkeypatch.setattr(proc, "_platform", lambda: platform)
    monkeypatch.setattr(proc, "_linux_stat", lambda pid: pytest.fail("read /proc"))
    assert proc.pid_alive(os.getpid())
    assert proc.pid_start_token(os.getpid())


def test_the_ps_path_reports_a_finished_child_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc, "_platform", lambda: "darwin")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not proc.pid_alive(child.pid)
    assert proc.pid_start_token(child.pid) == ""


@pytest.mark.skipif(sys.platform == "win32", reason="the walk reads ps")
def test_descendants_list_a_grandchild_before_its_parent() -> None:
    script = "import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print(c.pid, flush=True); time.sleep(60)"
    with subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout is not None
            grandchild = int(child.stdout.readline())
            below = proc.pid_descendants(os.getpid())
            assert grandchild in proc.pid_descendants(child.pid)
            assert below.index(grandchild) < below.index(child.pid)
        finally:
            for pid in [*proc.pid_descendants(child.pid), child.pid]:
                try:
                    os.kill(pid, 9)
                except ProcessLookupError:
                    pass


def test_a_finished_pid_has_no_descendants() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert proc.pid_descendants(child.pid) == []
