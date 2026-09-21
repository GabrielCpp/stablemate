"""Kill what a round left running."""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

GRACE_SECONDS = 5.0

PROC = Path("/proc")


@dataclass(frozen=True, slots=True)
class Survivor:
    """One process the round left behind, as it looked when the reaper found it."""

    pid: int
    cmdline: str

    def __str__(self) -> str:
        return f"pid {self.pid}: {self.cmdline}"


def _cmdline(pid: int) -> str:
    try:
        raw = (PROC / str(pid) / "cmdline").read_bytes()
    except OSError:
        return "<gone>"
    return " ".join(part for part in raw.decode("utf-8", "replace").split("\0") if part)


def survivors(stage: Path, *, exclude: frozenset[int] = frozenset()) -> list[Survivor]:
    """Every live process whose working directory is inside `stage`."""
    if not PROC.is_dir():
        logger.warning(
            "no /proc on this platform: a round cannot reap what it started, so a "
            "leftover process from %s will outlive it",
            stage,
        )
        return []
    root = stage.resolve()
    found: list[Survivor] = []
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in exclude or pid == os.getpid():
            continue
        try:
            cwd = (entry / "cwd").resolve()
        except OSError:
            continue
        if cwd == root or root in cwd.parents:
            found.append(Survivor(pid=pid, cmdline=_cmdline(pid)))
    return found


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap(stage: Path, *, exclude: frozenset[int] = frozenset()) -> list[Survivor]:
    """Terminate everything still standing in `stage`; return what was there."""
    left = survivors(stage, exclude=exclude)
    if not left:
        return []
    for proc in left:
        logger.warning("round left a process running, terminating — %s", proc)
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except OSError:
            continue

    deadline = time.monotonic() + GRACE_SECONDS
    pending = [p for p in left if _alive(p.pid)]
    while pending and time.monotonic() < deadline:
        time.sleep(0.1)
        pending = [p for p in pending if _alive(p.pid)]

    for proc in pending:
        logger.warning("%s ignored SIGTERM for %.0fs, killing", proc, GRACE_SECONDS)
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except OSError:
            continue
    return left
