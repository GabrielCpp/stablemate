"""The browser the dynamic tests start cannot subscribe to the host's network changes."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

import _quiet_chromium

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.uname().machine != "x86_64",
    reason="the socket filter is written for Linux on x86_64",
)

PROBE = """
import socket
try:
    socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0).close()
    print("route netlink opened")
except PermissionError:
    print("route netlink refused")
socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close()
print("ordinary sockets opened")
"""


def _probe(command: list[str]) -> list[str]:
    done = subprocess.run(
        [*command, "-c", PROBE], env={**os.environ, _quiet_chromium.REAL: sys.executable},
        capture_output=True, text=True, timeout=60, check=True,
    )
    return done.stdout.split("\n")[:2]


def test_a_program_started_through_the_wrapper_cannot_listen_for_network_changes():
    assert _probe([sys.executable]) == ["route netlink opened", "ordinary sockets opened"]
    assert _probe([sys.executable, _quiet_chromium.__file__]) == ["route netlink refused", "ordinary sockets opened"]
