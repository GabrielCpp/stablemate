"""A book run fails on each local service the app called that no runbook step starts, and a call the watch reports was made."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from workhorse_workflows.okf_book.shared import local_calls
from workhorse_workflows.okf_book.shared.local_calls import CallWatch, Machine, Runbook, Socket, Watch, read_runbook

APP = 10
OTHER = 20
LISTENER = 1
ESTABLISHED = "01"
CLOSE_WAIT = "08"
LISTEN = "0A"


@dataclass
class _Machine:
    sockets: dict[int, Socket] = field(default_factory=dict[int, Socket])
    held: dict[int, set[int]] = field(default_factory=dict[int, set[int]])

    def machine(self) -> Machine:
        return Machine(sockets=lambda: dict(self.sockets), pids=lambda: list(self.held),
                       socket_inodes=lambda pid: frozenset(self.held.get(pid, ())), command=lambda pid: f"process {pid}")

    def opens(self, pid: int, inode: int, socket: Socket | None) -> None:
        self.held.setdefault(pid, set()).add(inode)
        if socket is not None:
            self.sockets[inode] = socket


def _call(remote_port: int, *, loopback: bool = True, state: str = ESTABLISHED) -> Socket:
    return Socket(local_port=40000, remote_port=remote_port, remote_loopback=loopback, state=state)


def _serving(*ports: int) -> tuple[_Machine, Watch]:
    """The app listening on 5173 and every port of `ports`, and a watch that found it."""
    machine = _Machine()
    for inode, port in enumerate((5173, *ports), start=LISTENER):
        machine.opens(APP, inode, Socket(local_port=port, remote_port=0, remote_loopback=False, state=LISTEN))
    machine.opens(OTHER, 99, _call(8080))
    watch = Watch(named=frozenset({5173, 9099}), machine=machine.machine())
    watch.rescan()
    return machine, watch


def test_the_app_calling_a_loopback_port_no_runbook_names_is_a_call() -> None:
    machine, watch = _serving()
    machine.opens(APP, 50, _call(8080))

    watch.poll()

    assert watch.calls == {8080: {f"process {APP}"}}


def test_a_call_the_service_already_hung_up_on_is_a_call() -> None:
    machine, watch = _serving()
    machine.opens(APP, 50, _call(8081, state=CLOSE_WAIT))

    watch.poll()

    assert watch.calls == {8081: {f"process {APP}"}}


def test_a_call_to_a_named_port_a_served_port_or_another_host_is_no_call() -> None:
    machine, watch = _serving(24678)
    machine.opens(APP, 50, _call(9099))
    machine.opens(APP, 51, _call(24678))
    machine.opens(APP, 52, _call(443, loopback=False))
    machine.opens(APP, 53, Socket(local_port=5173, remote_port=51000, remote_loopback=True, state=ESTABLISHED))

    watch.poll()

    assert watch.calls == {}


def test_a_process_that_serves_no_named_port_is_not_watched() -> None:
    machine, watch = _serving()
    machine.opens(OTHER, 50, _call(8081))

    watch.poll()

    assert watch.calls == {}


def test_a_socket_the_table_has_not_listed_yet_is_read_again() -> None:
    machine, watch = _serving()
    machine.opens(APP, 50, None)

    watch.poll()
    machine.sockets[50] = _call(8081)
    watch.poll()

    assert watch.calls == {8081: {f"process {APP}"}}


def test_a_socket_the_table_never_lists_is_dropped() -> None:
    machine, watch = _serving()
    machine.opens(APP, 50, None)

    for _ in range(local_calls.TRIES + 1):
        watch.poll()
    machine.sockets[50] = _call(8081)
    watch.poll()

    assert watch.calls == {}


def test_a_runbook_names_the_ports_of_its_bullets_and_not_of_its_prose(tmp_path: Path) -> None:
    page = "docs/features/web-app/ops/dev.md"
    (tmp_path / page).parent.mkdir(parents=True)
    _ = (tmp_path / page).write_text(
        "# Dev\n\nThe dev server proxies `/api` to `http://localhost:8080`.\n\n"
        "- entry-url: http://localhost:5173/\n- run: PORT=4180 node server.mjs\n- run: npx vite --port 24678\n",
        encoding="utf-8")

    assert read_runbook(tmp_path, page) == Runbook(page=page, ports=frozenset({5173, 4180, 24678}))


def test_each_unstarted_port_names_who_called_it_and_the_runbooks_that_do_not_start_it() -> None:
    calls = CallWatch((Runbook("docs/features/web-app/ops/dev.md", frozenset({5173})),))
    calls.calls = {8080: ("`node vite dev` in /repo/web",)}

    [problem] = calls.unstarted()

    assert problem.startswith("while the book ran, `node vite dev` in /repo/web called localhost:8080, and no step of the runbooks "
                              + "docs/features/web-app/ops/dev.md starts or names that port.")


def test_a_watch_with_no_named_port_starts_nothing() -> None:
    with CallWatch(()) as calls:
        pass

    assert calls.unstarted() == ()


@pytest.mark.skipif(not local_calls.PROC.is_dir(), reason="the watch reads /proc")
def test_the_watch_sees_this_process_call_a_server_another_process_runs() -> None:
    with HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as named, HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) as other:
        port = other.server_port
        with subprocess.Popen([sys.executable, "-c", _ANSWER, str(other.fileno())], pass_fds=(other.fileno(),)) as answering:
            other.server_close()
            try:
                with CallWatch((Runbook("docs/features/web-app/ops/dev.md", frozenset({named.server_port})),)) as calls:
                    until = time.monotonic() + local_calls.RESCAN_S + 1
                    while time.monotonic() < until:
                        with socket.create_connection(("127.0.0.1", port)):
                            time.sleep(0.02)
            finally:
                answering.kill()

    assert port in calls.calls


_ANSWER = """
import socket
import sys
server = socket.socket(fileno=int(sys.argv[1]))
while True:
    server.accept()[0].close()
"""
