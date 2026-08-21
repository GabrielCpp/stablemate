"""Kill what a round left running.

A round's steps drive real agents, and a real agent starts real long-lived things: a Go
server it built so it could get a `201` out of it, a `go test` that forked a helper, a
watcher. Nothing guarantees the agent stops them. When the round ends they are still
holding their ports, and the next round on the same task asks for the same port and finds
it taken — by a *sibling*, which is the one intruder that looks exactly like success.

That is not hypothetical. A link-shortener round parked at its operator gate because
another round's server, days old, was answering `POST /links` on 18081 with a valid
`201 Created`. The coder lane was right to refuse it — it compared the listening binary's
SHA-256 against its own build and they differed — but the whole episode was self-inflicted:
the earlier round should never have been able to leave that process behind.

So the reaper runs when the steps do, whether they finished, failed, or raised. The rule it
enforces is deliberately narrow and mechanical: **a process whose working directory is
inside this round's stage belongs to this round.** No port list, no name matching, no
"agent-looking" heuristic — the stage is a directory only this round has, so anything
standing in it was put there by this round and has no reader once the round is over.

What it does not cover, and does not pretend to: a container (its cwd is inside the
container's namespace, not the stage), a daemon the agent started with a cwd elsewhere, a
process on another machine. Those need the thing that started them to clean up after
itself. This closes the case that actually bit us and reports what it closed, rather than
guessing at the ones it cannot see.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: How long a process gets to exit on SIGTERM before the reaper stops asking. Servers with
#: nothing in flight go instantly; the budget is for one that is mid-write, so it closes
#: its file rather than leaving the stage — which is about to be zipped — half-written.
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
    """Every live process whose working directory is inside `stage`.

    `exclude` is for the caller that is itself standing in the stage — a test, or a step
    that chose to work there. Without it the reaper would happily kill its own caller.
    """
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
            # Died between the listing and the readlink, or belongs to another user.
            # Either way there is nothing here to kill.
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
    """Terminate everything still standing in `stage`; return what was there.

    Every survivor is logged at WARNING with its command line, because a round that
    silently tidied up teaches nobody that the agent leaks — and the leak is the bug. The
    reaper is the net, not the fix.
    """
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
