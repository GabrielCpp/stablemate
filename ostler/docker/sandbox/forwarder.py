"""Bind loopback ports inside the sandbox and forward them to named upstreams.

This exists for one reason: QA plans hardcode `http://localhost:8090` *inside scenario
bodies*, not only in `target(base_url=...)`. Rewriting the target's base URL therefore
does not move a plan into a container, and editing every literal would mean the plan you
ran is not the plan that was reviewed.

So the container keeps `localhost` meaning what the plan thinks it means, and the map
from a loopback port to a real upstream — a compose service name, or the host gateway —
is configuration the *repo* owns (`qa-stack.yml`), not something a scenario can widen.
A port that is not in the map is not reachable, which is the whole permission model.

Stdlib only, and deliberately: this runs in an image that must not need a package index.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path

#: How long a single relay socket may sit idle before we stop waiting on it. Generous:
#: a QA scenario legitimately holds an idle connection open across a slow assertion.
IDLE_TIMEOUT = 900.0

BUFFER = 65536


def _pump(source: socket.socket, sink: socket.socket) -> None:
    """Copy one direction until it dries up, then half-close so the peer sees EOF.

    Half-closing rather than closing outright is what makes a request/response protocol
    work through the relay: an HTTP client that shuts down its write side is signalling
    "body complete", and a relay that turned that into a full close would drop the
    response it is waiting for.
    """
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
        # Closing without a byte is the honest signal. Synthesising an HTTP error would
        # be a lie for a non-HTTP upstream, and the plan's own connection error names
        # the port, which is the thing worth knowing.
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
        # Loopback only. Binding 0.0.0.0 would publish every mapped upstream to the whole
        # compose network under a new name, which is a hole nobody asked for.
        listener.bind(("127.0.0.1", int(port)))
        listener.listen(128)
        listeners.append(listener)
        threading.Thread(
            target=_serve, args=(listener, host, int(upstream_port)), daemon=True
        ).start()
        print(f"forwarder: 127.0.0.1:{port} -> {host}:{upstream_port}", flush=True)

    # Every socket is bound *before* this line, so the entrypoint that waits on this file
    # is waiting on a real guarantee: a scenario started afterwards cannot lose a race to
    # a listener that is not up yet. Binding is what has to happen first — accepting can
    # follow at its leisure, because the kernel queues.
    if ready_path is not None:
        ready_path.write_text(f"{len(listeners)}\n", encoding="utf-8")

    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
