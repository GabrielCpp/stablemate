"""The ports on this machine the app called while its book ran, and which of them no runbook step starts or names.

A call reaches whatever already listens on its port. Here that may be a service someone else
started, so a claim that needs it passes on this machine and fails on any other. The watch runs in
a process of its own, so the scenarios' threads cannot starve it. It reads the sockets the app's
servers hold every few milliseconds, and the machine's TCP table each time one of them opens a
new one. A call it misses is a call the run does not report, and a call it reports was made.
"""
from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType

from pydantic import TypeAdapter, ValidationError

PROC = Path("/proc")
POLL_S = 0.002
RESCAN_S = 2.0
TRIES = 3
_LISTEN = "0A"
_SOCKET = re.compile(r"^socket:\[(\d+)\]$")
_PORT = re.compile(r"(?::|\bPORT=|--port[= ])(\d{2,5})\b")
_BULLET = re.compile(r"^\s*- .*$", re.MULTILINE)
_IPV6_LOOPBACK = "00000000000000000000000001000000"
_IPV4_MAPPED = "0000000000000000FFFF0000"
_CALLS = TypeAdapter(dict[int, tuple[str, ...]])


@dataclass(frozen=True, slots=True)
class Runbook:
    """A runbook page and every port its bullets name."""

    page: str
    ports: frozenset[int]


@dataclass(frozen=True, slots=True)
class Socket:
    """One row of the machine's TCP table."""

    local_port: int
    remote_port: int
    remote_loopback: bool
    state: str


@dataclass(frozen=True, slots=True)
class Machine:
    """What the watch reads of this machine: its TCP table, its processes, the socket inodes each holds, and how each was started."""

    sockets: Callable[[], dict[int, Socket]]
    pids: Callable[[], Iterable[int]]
    socket_inodes: Callable[[int], frozenset[int]]
    command: Callable[[int], str]


def read_runbook(root: Path, page: str) -> Runbook:
    """The runbook at `page`, with the ports its bullets name. Its prose names none, since prose starts nothing."""
    bullets = "\n".join(_BULLET.findall((root / page).read_text(encoding="utf-8")))
    return Runbook(page=page, ports=frozenset(int(match.group(1)) for match in _PORT.finditer(bullets)))


def _loopback(host: str) -> bool:
    host = host.upper()
    if len(host) == 8:
        return host.endswith("7F")
    return host == _IPV6_LOOPBACK or (host.startswith(_IPV4_MAPPED) and host.endswith("7F"))


def _proc_sockets() -> dict[int, Socket]:
    found: dict[int, Socket] = {}
    for table in ("tcp", "tcp6"):
        try:
            rows = (PROC / "net" / table).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) < 10 or fields[9] == "0":
                continue
            local, remote = fields[1].split(":"), fields[2].split(":")
            found[int(fields[9])] = Socket(local_port=int(local[1], 16), remote_port=int(remote[1], 16),
                                           remote_loopback=_loopback(remote[0]), state=fields[3].upper())
    return found


def _proc_pids() -> list[int]:
    try:
        return [int(entry.name) for entry in PROC.iterdir() if entry.name.isdigit() and int(entry.name) != os.getpid()]
    except OSError:
        return []


def _proc_socket_inodes(pid: int) -> frozenset[int]:
    folder = PROC / str(pid) / "fd"
    try:
        links = os.listdir(folder)
    except OSError:
        return frozenset()
    found: set[int] = set()
    for link in links:
        try:
            target = _SOCKET.match(os.readlink(folder / link))
        except OSError:
            continue
        if target:
            found.add(int(target.group(1)))
    return frozenset(found)


def _proc_command(pid: int) -> str:
    try:
        argv = [arg.decode(errors="replace") for arg in (PROC / str(pid) / "cmdline").read_bytes().split(b"\0") if arg]
        cwd = os.readlink(PROC / str(pid) / "cwd")
    except OSError:
        return f"process {pid}"
    return f"`{' '.join([Path(argv[0]).name, *argv[1:3]])}` in {cwd}" if argv else f"process {pid} in {cwd}"


PROC_MACHINE = Machine(sockets=_proc_sockets, pids=_proc_pids, socket_inodes=_proc_socket_inodes, command=_proc_command)


@dataclass
class Watch:
    """The app's servers, the processes that listen on a port a runbook names, and the loopback ports off the runbooks they called."""

    named: frozenset[int]
    machine: Machine = PROC_MACHINE
    calls: dict[int, set[str]] = field(default_factory=dict[int, set[str]])
    _held: dict[int, frozenset[int]] = field(default_factory=dict[int, frozenset[int]])
    _served: frozenset[int] = frozenset()
    _pending: dict[int, tuple[int, int]] = field(default_factory=dict[int, tuple[int, int]])

    def rescan(self) -> None:
        """Find the app's servers among every process, and the ports they serve."""
        sockets = self.machine.sockets()
        held = {pid: self.machine.socket_inodes(pid) for pid in self.machine.pids()}
        listening = {pid: {sockets[inode].local_port for inode in inodes if inode in sockets and sockets[inode].state == _LISTEN}
                     for pid, inodes in held.items()}
        apps = {pid for pid, ports in listening.items() if ports & self.named}
        self._served = frozenset(port for pid in apps for port in listening[pid])
        for pid in apps - self._held.keys():
            self._held[pid] = held[pid]
        for pid in self._held.keys() - apps:
            del self._held[pid]

    def poll(self) -> None:
        """Note each socket an app server opened since the last poll, and resolve the open ones against the TCP table."""
        for pid, before in list(self._held.items()):
            now = self.machine.socket_inodes(pid)
            self._held[pid] = now
            for inode in now - before:
                self._pending[inode] = (pid, TRIES)
        self._pending = {inode: owner for inode, owner in self._pending.items() if inode in self._held.get(owner[0], frozenset())}
        if not self._pending:
            return
        sockets = self.machine.sockets()
        for inode, (pid, tries) in list(self._pending.items()):
            row = sockets.get(inode)
            if row is None and tries > 1:
                self._pending[inode] = (pid, tries - 1)
                continue
            del self._pending[inode]
            if (row is not None and row.state != _LISTEN and row.remote_port and row.remote_loopback
                    and row.local_port not in self._served and row.remote_port not in self._served | self.named):
                self.calls.setdefault(row.remote_port, set()).add(self.machine.command(pid))


def watch(named: frozenset[int], until: Callable[[], bool], machine: Machine = PROC_MACHINE) -> dict[int, set[str]]:
    """Watch the app's servers until `until` says stop, and return the ports off the runbooks they called, with who called."""
    seen = Watch(named=named, machine=machine)
    scanned = 0.0
    while not until():
        if time.monotonic() - scanned >= RESCAN_S:
            seen.rescan()
            scanned = time.monotonic()
        seen.poll()
        time.sleep(POLL_S)
    return seen.calls


class CallWatch:
    """The watch, in a process of its own for as long as the book runs."""

    def __init__(self, runbooks: Sequence[Runbook]) -> None:
        self.runbooks = tuple(runbooks)
        self.named = frozenset[int]().union(*(runbook.ports for runbook in self.runbooks))
        self.calls: dict[int, tuple[str, ...]] = {}
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self) -> CallWatch:
        if self.named and PROC.is_dir():
            self._process = subprocess.Popen(
                [sys.executable, "-m", __name__, *map(str, sorted(self.named))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None) -> None:
        if self._process is None:
            return
        try:
            out, _ = self._process.communicate(input="", timeout=30)
        except subprocess.TimeoutExpired:
            self._process.kill()
            _ = self._process.communicate()
            return
        try:
            self.calls = _CALLS.validate_json(out or "{}")
        except ValidationError:
            self.calls = {}

    def unstarted(self) -> tuple[str, ...]:
        """One problem per port the app called that no runbook bullet names."""
        pages = ", ".join(runbook.page for runbook in self.runbooks)
        return tuple(
            f"while the book ran, {', '.join(sorted(callers))} called localhost:{port}, and no step of the runbooks "
            + f"{pages} starts or names that port. Whatever answered there was already running on this machine, "
            + "so every claim that reached it passes only here, and on another machine nothing answers. Start "
            + "that service in a runbook step on a free port, and set the address the app's source calls it at, "
            + "such as a dev proxy's target, to that port"
            for port, callers in sorted(self.calls.items()))


def main(argv: Sequence[str] | None = None) -> None:
    """Watch until stdin closes, then print the calls as JSON."""

    def closed() -> bool:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(ready) and sys.stdin.read() == ""

    calls = watch(frozenset(int(port) for port in (sys.argv[1:] if argv is None else argv)), closed)
    print(json.dumps({str(port): sorted(callers) for port, callers in calls.items()}))


if __name__ == "__main__":
    main()
