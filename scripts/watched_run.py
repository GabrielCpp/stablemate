#!/usr/bin/env python3
"""Run a long command so that its death cannot be silent.

A benchmark round is hours long, and the agent that launched it is not watching. When
such a run disappears — an OOM kill, a harness reaping its background tasks, a laptop
suspending — the evidence it leaves behind is *nothing*: an empty log, no exit code, no
record that it ever started. The next thing anyone sees is a result that never arrived,
and the natural reading of an empty log is "it printed nothing", not "it was killed".

The design turns on one fact: **a process killed by SIGKILL cannot report its own
death.** No handler runs, no `finally` executes, no atexit fires. So a run cannot be
made to announce that it died; something else has to notice that it stopped.

Three records, each covering the failure the one before it cannot:

- **The tombstone.** A supervisor parent waits on the command and writes down how it
  ended — exit code, or the signal that took it. This covers the ordinary case, where
  the command dies and its parent does not.
- **The heartbeat.** The supervisor stamps the status file every few seconds. When the
  whole process group is killed at once, the supervisor dies with its child and writes
  no tombstone — and then the *absence* of a fresh heartbeat is the only surviving
  evidence. A stale heartbeat with no tombstone is a death, and `check` says so.
- **The attribution.** Once a death is known, `journalctl -k` is asked whether the
  kernel killed it for memory. Best-effort: it answers on a machine that keeps a kernel
  log readable, and stays quiet on one that does not. "Vanished" is already actionable;
  "vanished, OOM-killed at 16:54" is diagnosable.

What this does **not** do is prevent an OOM kill. An unprivileged process cannot lower
its own `oom_score_adj` below zero — the kernel only lets you volunteer as a *better*
victim, never a worse one — so there is no flag here that buys survival. Reducing the
pressure is the only real protection, and that is a decision about what else is running
on the machine, not something a wrapper can take.

    scripts/watched_run.py start --name seat-rerun -- paddock run seat-booking-qa
    scripts/watched_run.py check                 # every run; nonzero if any vanished
    scripts/watched_run.py check --name seat-rerun

`start` detaches into its own session, so a sweep of the caller's process group leaves
it alone. That is protection against one specific killer and not against the others,
which is exactly why the records above exist.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

#: How often the supervisor stamps the status file.
HEARTBEAT_SECONDS = 10

#: Missed beats before a run with no tombstone is called dead. Three, so that a
#: momentarily stalled machine does not get a live run declared vanished.
STALE_BEATS = 3

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "stablemate" / "watched-runs"


def _state_dir(raw: str | None) -> Path:
    path = Path(raw).expanduser() if raw else DEFAULT_STATE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Record:
    """One run's status file, as it is read back."""

    path: Path
    data: dict[str, object]

    @property
    def name(self) -> str:
        return str(self.data.get("name", self.path.stem))

    @property
    def state(self) -> str:
        return str(self.data.get("state", "unknown"))

    def get_float(self, key: str) -> float:
        value = self.data.get(key)
        return float(value) if isinstance(value, int | float) else 0.0

    def get_int(self, key: str) -> int:
        value = self.data.get(key)
        return int(value) if isinstance(value, int | float) else 0


def _write(path: Path, data: dict[str, object]) -> None:
    """Replace the status file atomically, so a reader never sees half a record."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _alive(pid: int) -> bool:
    """Is this pid a process that is still running?

    A zombie answers `kill(pid, 0)` successfully — it holds its pid until its parent
    reaps it — so signalling alone would report a supervisor that died seconds ago as
    healthy, and the death would wait on the heartbeat going stale instead. `/proc`
    is asked for the state so the answer is about running, not about existing.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    # The comm field is parenthesised and may itself contain spaces; state follows it.
    return stat.rpartition(")")[2].split()[0] != "Z"


def _oom_evidence(pids: list[int], since_epoch: float) -> str | None:
    """Ask the kernel log whether it killed one of these pids for memory.

    Best-effort by design: `journalctl` may be absent, restricted, or keep no kernel
    log at all. A machine that cannot answer gets no answer, not a failed check.
    """
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(max(0.0, since_epoch - 60)))
    try:
        proc = subprocess.run(
            ["journalctl", "-k", "--since", since, "--no-pager"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    wanted = {str(pid) for pid in pids}
    for line in proc.stdout.splitlines():
        lowered = line.lower()
        if "out of memory" not in lowered and "oom-kill" not in lowered:
            continue
        if any(pid in line for pid in wanted):
            return line.strip()
    return None


def _supervise(args: argparse.Namespace, status: Path, log: Path) -> int:
    """The detached parent: run the command, beat, and write down how it ended."""
    os.setsid()
    started = time.time()
    handle = log.open("wb", buffering=0)
    with contextlib.suppress(OSError):
        os.close(0)
        os.open(os.devnull, os.O_RDONLY)

    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(args.command, stdout=handle, stderr=handle, stdin=subprocess.DEVNULL, env=env)

    record: dict[str, object] = {
        "name": args.name,
        "state": "running",
        "command": args.command,
        "cwd": os.getcwd(),
        "log": str(log),
        "pid": proc.pid,
        "supervisor_pid": os.getpid(),
        "started_at": started,
        "heartbeat": started,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
    }
    _write(status, record)

    forwarded: list[int] = []

    def relay(signum: int, _frame: object) -> None:
        """Pass a polite stop down, and remember that we were asked."""
        forwarded.append(signum)
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, relay)

    last_beat = started
    while proc.poll() is None:
        time.sleep(0.5)
        now = time.time()
        if now - last_beat >= HEARTBEAT_SECONDS:
            last_beat = now
            record["heartbeat"] = now
            _write(status, record)

    code = proc.returncode
    record["heartbeat"] = time.time()
    record["ended_at"] = time.time()
    record["returncode"] = code
    if code < 0:
        record["state"] = "signaled"
        record["signal"] = signal.Signals(-code).name
        record["oom"] = _oom_evidence([proc.pid, os.getpid()], started)
    else:
        record["state"] = "exited"
    if forwarded:
        record["forwarded_signals"] = [signal.Signals(s).name for s in forwarded]
    _write(status, record)
    handle.close()
    return 0 if code == 0 else 1


def cmd_start(args: argparse.Namespace) -> int:
    directory = _state_dir(args.dir)
    status = directory / f"{args.name}.json"
    log = directory / f"{args.name}.log"
    if status.exists():
        existing = Record(status, json.loads(status.read_text()))
        if existing.state == "running" and _alive(existing.get_int("supervisor_pid")):
            print(f"{args.name}: already running (supervisor {existing.get_int('supervisor_pid')})", file=sys.stderr)
            return 2
    log.write_text("")

    if os.fork() != 0:
        # Give the child long enough to write the first record, so `check` immediately
        # after `start` describes a run rather than an absence.
        for _ in range(40):
            if status.exists():
                break
            time.sleep(0.05)
        print(f"name    {args.name}")
        print(f"status  {status}")
        print(f"log     {log}")
        print(f"check   {Path(__file__).resolve()} check --name {args.name}")
        return 0
    os._exit(_supervise(args, status, log))


def _classify(record: Record) -> tuple[str, str]:
    """Return (verdict, detail) for one status file, recording a death if it finds one."""
    now = time.time()
    if record.state == "exited":
        code = record.get_int("returncode")
        took = record.get_float("ended_at") - record.get_float("started_at")
        return ("ok" if code == 0 else "failed", f"exit {code} after {took / 60:.1f}m")
    if record.state == "signaled":
        detail = f"killed by {record.data.get('signal')}"
        if record.data.get("oom"):
            detail += " — OOM: " + str(record.data["oom"])
        return ("killed", detail)
    if record.state == "vanished":
        return ("vanished", str(record.data.get("detail", "no tombstone, heartbeat stopped")))

    age = now - record.get_float("heartbeat")
    supervisor = record.get_int("supervisor_pid")
    if _alive(supervisor) and age < HEARTBEAT_SECONDS * STALE_BEATS:
        elapsed = (now - record.get_float("started_at")) / 60
        return ("running", f"pid {record.get_int('pid')}, {elapsed:.1f}m elapsed")

    # No tombstone and no heartbeat: the supervisor was killed alongside its child, so
    # nothing was left alive to write down what happened. This is the case the whole
    # file exists for — record it now, while the kernel log still remembers.
    oom = _oom_evidence([record.get_int("pid"), supervisor], record.get_float("started_at"))
    detail = f"no tombstone; last heartbeat {age / 60:.1f}m ago"
    if oom:
        detail += " — OOM: " + oom
    data = dict(record.data)
    data["state"] = "vanished"
    data["detail"] = detail
    data["oom"] = oom
    _write(record.path, data)
    return ("vanished", detail)


def cmd_check(args: argparse.Namespace) -> int:
    directory = _state_dir(args.dir)
    paths = [directory / f"{args.name}.json"] if args.name else sorted(directory.glob("*.json"))
    paths = [p for p in paths if p.exists()]
    if not paths:
        print("no watched runs")
        return 0

    rows = []
    for path in paths:
        try:
            record = Record(path, json.loads(path.read_text()))
        except (OSError, ValueError):
            rows.append((path.stem, "unreadable", str(path)))
            continue
        verdict, detail = _classify(record)
        rows.append((record.name, verdict, detail))

    width = max(len(name) for name, _, _ in rows)
    for name, verdict, detail in rows:
        print(f"{name.ljust(width)}  {verdict:9}  {detail}")
    return 1 if any(verdict in ("vanished", "killed", "failed") for _, verdict, _ in rows) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", help=f"state directory (default {DEFAULT_STATE_DIR})")
    sub = parser.add_subparsers(dest="action", required=True)

    start = sub.add_parser("start", help="run a command detached, watched")
    start.add_argument("--name", required=True)
    start.add_argument("command", nargs=argparse.REMAINDER)
    start.set_defaults(func=cmd_start)

    check = sub.add_parser("check", help="report every watched run; nonzero if any died")
    check.add_argument("--name")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if args.action == "start":
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if not args.command:
            parser.error("start needs a command, after `--`")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
