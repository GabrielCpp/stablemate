"""The daemon's wire format: one newline-terminated JSON request, one reply."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs

SOCKET_FILE = "saddlebag.sock"
REQUEST_LIMIT = 64 * 1024
REPLY_LIMIT = 4 * 1024 * 1024
CONNECT_RETRY_S = 0.05
DEFAULT_TIMEOUT = 120.0

_SUN_PATH_MAX = 100
_CHUNK = 64 * 1024


class DaemonNotRunning(RuntimeError):
    """No daemon answers on the socket."""


class ProtocolError(ValueError):
    """A message was not valid on the wire."""


@dataclass(frozen=True)
class Request:
    """A verb and its arguments."""

    verb: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"verb": self.verb, "args": self.args})

    @classmethod
    def from_json(cls, raw: str) -> Request:
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ProtocolError("the request is not JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("verb"), str):
            raise ProtocolError("the request needs a string 'verb'")
        args = payload.get("args", {})
        if not isinstance(args, dict):
            raise ProtocolError("'args' must be an object")
        return cls(payload["verb"], args)


@dataclass(frozen=True)
class Reply:
    """The outcome of a request."""

    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps({"ok": self.ok, "result": self.result, "error": self.error})

    @classmethod
    def from_json(cls, raw: str) -> Reply:
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ProtocolError("the reply is not JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            raise ProtocolError("the reply needs a boolean 'ok'")
        result = payload.get("result") or {}
        if not isinstance(result, dict):
            raise ProtocolError("'result' must be an object")
        error = payload.get("error")
        return cls(payload["ok"], result, error if isinstance(error, str) else None)


def socket_path() -> Path:
    """Where the daemon listens, shortened when the natural path would not fit a unix socket."""
    explicit = os.environ.get("SADDLEBAG_SOCKET")
    if explicit:
        return fit_socket_path(Path(explicit))
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime else Path(platformdirs.user_runtime_dir("saddlebag"))
    return fit_socket_path(base / SOCKET_FILE)


def fit_socket_path(path: Path) -> Path:
    """``path`` itself, or a short temp path derived from it when it exceeds sun_path."""
    if len(str(path)) <= _SUN_PATH_MAX:
        return path
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"saddlebag-{digest}.sock"


def read_message(conn: socket.socket, *, limit: int) -> str:
    """One newline-terminated message, reassembled across however many packets it arrives in."""
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
                raise ProtocolError(f"message exceeded {limit} bytes")
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ProtocolError(f"message exceeded {limit} bytes with no newline")
    return b"".join(chunks).decode("utf-8", errors="replace")


def write_message(conn: socket.socket, text: str) -> None:
    conn.sendall((text + "\n").encode("utf-8"))


def is_live(path: Path) -> bool:
    """Whether something is listening on ``path`` right now."""
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        probe.connect(str(path))
    except OSError:
        return False
    else:
        return True
    finally:
        probe.close()


def _connected(path: Path, timeout: float) -> socket.socket:
    deadline = time.monotonic() + timeout
    while True:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            client.close()
            raise DaemonNotRunning(f"no saddlebag daemon on {path}: start one with `saddlebag serve`") from exc
        except BlockingIOError as exc:
            client.close()
            if time.monotonic() >= deadline:
                raise DaemonNotRunning(f"the daemon on {path} took no request for {timeout:g}s") from exc
            time.sleep(CONNECT_RETRY_S)
        else:
            return client


def send(request: Request, *, timeout: float = DEFAULT_TIMEOUT) -> Reply:
    """Deliver ``request`` to the daemon and return its reply."""
    path = socket_path()
    client = _connected(path, timeout)
    try:
        write_message(client, request.to_json())
        raw = read_message(client, limit=REPLY_LIMIT)
    except TimeoutError as exc:
        raise DaemonNotRunning(f"the daemon on {path} gave no answer within {timeout:g}s") from exc
    finally:
        client.close()
    if not raw:
        raise DaemonNotRunning(f"the daemon on {path} closed the connection without a reply")
    return Reply.from_json(raw)
