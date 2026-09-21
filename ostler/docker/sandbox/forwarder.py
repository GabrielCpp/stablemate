"""Bind loopback ports inside the sandbox and forward them to named upstreams."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path

IDLE_TIMEOUT = 900.0

BUFFER = 65536


def _pump(source: socket.socket, sink: socket.socket) -> None:
    """Copy one direction until it dries up, then half-close so the peer sees EOF."""
    try:
        while True:
            chunk = source.recv(BUFFER)
            if not chunk:
                break
            sink.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            sink.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _relay(client: socket.socket, upstream_host: str, upstream_port: int) -> None:
    try:
        upstream = socket.create_connection((upstream_host, upstream_port), timeout=30)
    except OSError as exc:
        print(f"forwarder: {upstream_host}:{upstream_port} unreachable: {exc}", file=sys.stderr, flush=True)
        client.close()
        return
    client.settimeout(IDLE_TIMEOUT)
    upstream.settimeout(IDLE_TIMEOUT)
    outbound = threading.Thread(target=_pump, args=(client, upstream), daemon=True)
    outbound.start()
    _pump(upstream, client)
    outbound.join(timeout=IDLE_TIMEOUT)
    client.close()
    upstream.close()


def _serve(listener: socket.socket, upstream_host: str, upstream_port: int) -> None:
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        threading.Thread(
            target=_relay, args=(client, upstream_host, upstream_port), daemon=True
        ).start()


def main(argv: list[str]) -> int:
    raw = os.environ.get("OSTLER_SANDBOX_FORWARD", "").strip()
    ready_path = Path(argv[0]) if argv else None
    mapping: dict[str, str] = json.loads(raw) if raw else {}

    listeners: list[socket.socket] = []
    for port, upstream in sorted(mapping.items()):
        host, _, upstream_port = upstream.rpartition(":")
        if not host:
            print(f"forwarder: bad upstream {upstream!r} for port {port}", file=sys.stderr, flush=True)
            return 2
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", int(port)))
        listener.listen(128)
        listeners.append(listener)
        threading.Thread(
            target=_serve, args=(listener, host, int(upstream_port)), daemon=True
        ).start()
        print(f"forwarder: 127.0.0.1:{port} -> {host}:{upstream_port}", flush=True)

    if ready_path is not None:
        ready_path.write_text(f"{len(listeners)}\n", encoding="utf-8")

    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
