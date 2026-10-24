"""The daemon: it holds the Vault token and answers verbs on a unix socket."""

from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

from saddlebag import browser
from saddlebag.protocol import REQUEST_LIMIT, ProtocolError, Reply, Request, is_live, read_message, write_message
from saddlebag.store import SecretStore
from saddlebag.verbs import Verbs

logger = logging.getLogger(__name__)

BACKLOG = 8
CONNECTION_TIMEOUT = 5.0
ACCEPT_TICK = 0.2


def _bind(path: Path) -> socket.socket:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if is_live(path):
            raise OSError(f"another saddlebag daemon is already listening on {path}")
        path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(BACKLOG)
    except OSError:
        listener.close()
        raise
    listener.settimeout(ACCEPT_TICK)
    return listener


def _answer(daemon: Verbs, conn: socket.socket) -> None:
    conn.settimeout(CONNECTION_TIMEOUT)
    try:
        raw = read_message(conn, limit=REQUEST_LIMIT)
        if not raw:
            return
        request = Request.from_json(raw)
    except (OSError, ProtocolError) as exc:
        logger.warning("ignoring an unreadable request: %s", exc)
        try:
            write_message(conn, Reply(False, error=f"unreadable request: {exc}").to_json())
        except OSError:
            pass
        return
    reply = daemon.handle(request)
    conn.settimeout(None)
    try:
        write_message(conn, reply.to_json())
    except OSError as exc:
        logger.debug("reply not delivered: %s", exc)


def serve(
    store: SecretStore,
    *,
    socket_path: Path,
    browser_endpoint: str = browser.DEFAULT_ENDPOINT,
    ready: threading.Event | None = None,
    stop: threading.Event | None = None,
    token_source: str | None = None,
) -> None:
    """Answer requests one at a time until ``stop`` is set."""
    listener = _bind(socket_path)
    daemon = Verbs(store, browser_endpoint, f"socket {socket_path}", token_source)
    logger.info("listening on %s", socket_path)
    if ready is not None:
        ready.set()
    try:
        while stop is None or not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            with conn:
                _answer(daemon, conn)
    finally:
        listener.close()
        socket_path.unlink(missing_ok=True)
