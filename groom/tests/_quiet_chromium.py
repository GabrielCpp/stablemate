#!/usr/bin/env python3
"""Chromium for the dynamic tests, started so that it cannot hear the host's network.

Chromium listens on a route netlink socket and fails every request that is still
connecting with ERR_NETWORK_CHANGED when an interface of the host comes or goes. A
container starting beside the suite is such a change, and the page under test then
loads without its script. This file runs as the browser executable: it forbids that
one socket, then becomes the real browser, which carries on without the listener.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from typing import Any

REAL = "QUIET_CHROMIUM_REAL"
ALLOW = 0x7FFF0000
REFUSE = 0x00050000 | 1
X86_64 = 0xC000003E
SOCKET = 41
AF_NETLINK = 16
NETLINK_ROUTE = 0
LOAD, EQUAL, RETURN = 0x20, 0x15, 0x06
ARCH, CALL, FAMILY, PROTOCOL = 4, 0, 16, 32
NO_NEW_PRIVS, SECCOMP, FILTER = 38, 22, 2
STEPS = (
    (LOAD, 0, 0, ARCH), (EQUAL, 0, 7, X86_64),
    (LOAD, 0, 0, CALL), (EQUAL, 0, 5, SOCKET),
    (LOAD, 0, 0, FAMILY), (EQUAL, 0, 3, AF_NETLINK),
    (LOAD, 0, 0, PROTOCOL), (EQUAL, 0, 1, NETLINK_ROUTE),
    (RETURN, 0, 0, REFUSE), (RETURN, 0, 0, ALLOW),
)


def launch(playwright: Any) -> Any:
    """A Chromium that hears no host network change, where this kernel can arrange it."""
    if not sys.platform.startswith("linux"):
        return playwright.chromium.launch()
    return playwright.chromium.launch(
        executable_path=__file__, env={**os.environ, REAL: playwright.chromium.executable_path}
    )


def refuse_route_netlink() -> None:
    """Make opening a route netlink socket fail in this process and all it starts."""
    code = ctypes.create_string_buffer(b"".join(struct.pack("HBBI", *step) for step in STEPS))
    program = struct.pack("HxxxxxxP", len(STEPS), ctypes.addressof(code))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(NO_NEW_PRIVS, 1, 0, 0, 0) or libc.prctl(SECCOMP, FILTER, ctypes.c_char_p(program), 0, 0):
        raise OSError(ctypes.get_errno(), "the kernel refused the socket filter")


def main() -> None:
    refuse_route_netlink()
    os.execv(os.environ[REAL], [os.environ[REAL], *sys.argv[1:]])


if __name__ == "__main__":
    main()
