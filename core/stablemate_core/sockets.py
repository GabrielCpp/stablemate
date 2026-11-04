"""Newline-framed messages over a unix socket: the framing and the connect-with-retry both sides of a local daemon share."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from pathlib import Path

_CHUNK = 64 * 1024


def read_message(conn: socket.socket, *, limit: int, error: Callable[[str], Exception] = ValueError) -> str:
    """One newline-terminated message, reassembled across however many packets it arrives in.

    A message over *limit* bytes raises ``error(message)``.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = conn.recv(_CHUNK)
        if not chunk:
            break
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            total += newline
            if total > limit:
                raise error(f"message exceeded {limit} bytes")
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise error(f"message exceeded {limit} bytes with no newline")
    return b"".join(chunks).decode("utf-8", errors="replace")


def connected(path: Path, timeout: float, *, retry_s: float) -> socket.socket:
    """A client connected to *path*, waiting up to *timeout* while the listener's queue is full.

    Raises ``FileNotFoundError`` when nothing listens on *path* and ``TimeoutError`` when the queue
    stayed full for *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    while True:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            client.close()
            raise FileNotFoundError(f"nothing is listening on {path}") from exc
        except BlockingIOError as exc:
            client.close()
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{path} took no request for {timeout:g}s: its queue stayed full") from exc
            time.sleep(retry_s)
        else:
            return client
