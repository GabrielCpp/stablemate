from __future__ import annotations

import socket
from pathlib import Path

import pytest

from stablemate_core.sockets import connected, read_message


class _Refused(ValueError):
    pass


def test_a_message_split_across_packets_is_reassembled() -> None:
    left, right = socket.socketpair()
    try:
        right.sendall(b"hel")
        right.sendall(b"lo\nignored")
        assert read_message(left, limit=1024) == "hello"
    finally:
        left.close()
        right.close()


def test_a_message_over_its_limit_raises_the_caller_s_error() -> None:
    left, right = socket.socketpair()
    try:
        right.sendall(b"y" * 4096)
        with pytest.raises(_Refused, match="exceeded 1024 bytes"):
            read_message(left, limit=1024, error=_Refused)
    finally:
        left.close()
        right.close()


def test_connecting_to_nothing_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connected(tmp_path / "none.sock", 0.2, retry_s=0.01)


def test_a_full_queue_times_out(tmp_path: Path) -> None:
    path = tmp_path / "s.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(0)
    held = [connected(path, 1.0, retry_s=0.01)]
    try:
        while True:
            try:
                held.append(connected(path, 0.1, retry_s=0.01))
            except TimeoutError:
                break
            if len(held) > 64:
                pytest.skip("the platform queue never filled")
    finally:
        for client in held:
            client.close()
        server.close()
