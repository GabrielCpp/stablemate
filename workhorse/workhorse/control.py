"""The one channel an operator says something to a live run over."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import select
import socket
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from workhorse._vendor.stablemate_core.clock import Clock

STATUS = "status"

QUESTIONS = "questions"

ANSWER = "answer"

STOP = "stop"

SOCKET_FILE = "control.sock"

POINTER_FILE = "control.sock.path"

_SUN_PATH_MAX = 100

_CHUNK = 64 * 1024

REQUEST_LIMIT = 64 * 1024

REPLY_LIMIT = 64 * 1024 * 1024

logger = logging.getLogger(__name__)


class ControlProtocolError(Exception):
    """A message that could not be framed: over its limit with no newline in sight."""


@dataclass(frozen=True)
class Request:
    """What an operator asked for, as it arrived on the channel."""

    action: str = "reload"
    core: bool = False
    at_boundary: bool = False
    cli: str = ""
    profile: str = ""
    path: str = ""
    body: str = ""
    requested_at: str = ""

    @property
    def cuts_the_turn(self) -> bool:
        """Whether this interrupts the streaming turn instead of waiting for a boundary."""
        return not self.at_boundary

    def to_json(self) -> str:
        return json.dumps(
            {
                "action": self.action,
                "core": self.core,
                "at_boundary": self.at_boundary,
                "cli": self.cli,
                "profile": self.profile,
                "path": self.path,
                "body": self.body,
                "requested_at": self.requested_at or datetime.now(UTC).isoformat(),
            }
        )

    @classmethod
    def from_raw(cls, raw: object) -> "Request | None":
        """A request from a decoded JSON payload, or None when it is not one."""
        if not isinstance(raw, dict):
            return None
        return cls(
            action=str(raw.get("action", "reload")),
            core=bool(raw.get("core", False)),
            at_boundary=bool(raw.get("at_boundary", False)),
            cli=str(raw.get("cli", "")),
            profile=str(raw.get("profile", "")),
            path=str(raw.get("path", "")),
            body=str(raw.get("body", "")),
            requested_at=str(raw.get("requested_at", "")),
        )


class ControlChannel(Protocol):
    """A source of operator requests that a `select` can wait on."""

    def fileno(self) -> int | None: ...

    def take(self) -> Request | None: ...

    def reply(self, payload: dict[str, object]) -> None: ...

    def close(self) -> None: ...


class NullChannel:
    """No channel at all: the default, and what every unit test gets."""

    def fileno(self) -> int | None:
        return None

    def take(self) -> Request | None:
        return None

    def reply(self, payload: dict[str, object]) -> None:
        return None

    def close(self) -> None:
        return None


NULL_CHANNEL = NullChannel()


class SocketChannel:
    """A `AF_UNIX` listener in the run dir, accepted from the caller's own `select`."""

    def __init__(self, path: Path, listener: socket.socket) -> None:
        self.path = path
        self._listener = listener
        self._conn: socket.socket | None = None

    @classmethod
    def open(cls, run_dir: str | Path) -> "SocketChannel":
        """Bind the channel for `run_dir`, replacing a socket no one is listening on."""
        directory = Path(run_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = _socket_path(directory)
        if path.exists():
            if _is_live(path):
                raise OSError(f"another run is already listening on {path}")
            path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        os.chmod(path, 0o600)
        listener.listen(1)
        listener.setblocking(False)
        return cls(path, listener)

    def fileno(self) -> int | None:
        return self._listener.fileno()

    def take(self) -> Request | None:
        """Accept a waiting connection and read its one request, or None."""
        self._drop_connection()
        try:
            conn, _ = self._listener.accept()
        except (BlockingIOError, OSError):
            return None
        conn.settimeout(2.0)
        try:
            raw = _read_message(conn, limit=REQUEST_LIMIT)
        except (OSError, ControlProtocolError) as exc:
            logger.warning("ignoring an unreadable control message: %s", exc)
            conn.close()
            return None
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            logger.warning("ignoring a control message that is not JSON: %s", exc)
            conn.close()
            return None
        request = Request.from_raw(payload)
        if request is None:
            logger.warning("ignoring a control message that is not a JSON object")
            conn.close()
            return None
        self._conn = conn
        return request

    def reply(self, payload: dict[str, object]) -> None:
        """Answer the request just taken, if its connection is still there."""
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError as exc:
            logger.debug("control reply not delivered: %s", exc)
        finally:
            conn.close()

    def close(self) -> None:
        self._drop_connection()
        try:
            self._listener.close()
        finally:
            self.path.unlink(missing_ok=True)
            pointer = self.path.parent / POINTER_FILE
            if pointer.name != self.path.name:
                pointer.unlink(missing_ok=True)

    def _drop_connection(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            conn.close()


class FakeChannel:
    """Scripted requests, for a test that wants the behaviour and not the socket."""

    def __init__(self, *requests: Request) -> None:
        self.pending: list[Request] = list(requests)
        self.replies: list[dict[str, object]] = []
        self.closed = False

    def fileno(self) -> int | None:
        return None

    def take(self) -> Request | None:
        return self.pending.pop(0) if self.pending else None

    def reply(self, payload: dict[str, object]) -> None:
        self.replies.append(payload)

    def close(self) -> None:
        self.closed = True


class _Watch:
    """The channel this process's run is reachable on, set once when the run starts."""

    channel: ControlChannel = NULL_CHANNEL
    held: Request | None = None
    report: Callable[[], dict[str, object]] | None = None
    asked: Callable[[], list[dict[str, object]]] | None = None


_watch = _Watch()


def arm(channel: ControlChannel | None) -> None:
    """Make `channel` the one this process answers on."""
    _watch.channel = channel or NULL_CHANNEL
    _watch.held = None
    if channel is None:
        _watch.report = None
        _watch.asked = None


def report_with(describe: Callable[[], dict[str, object]] | None) -> None:
    """Say how this process answers `status`."""
    _watch.report = describe


def questions_with(pending: Callable[[], list[dict[str, object]]] | None) -> None:
    """Say what this run is blocked asking an operator."""
    _watch.asked = pending


def armed() -> ControlChannel:
    """The installed channel — `NULL_CHANNEL` when no run is attached."""
    return _watch.channel


def _delivered(channel: ControlChannel) -> Request | None:
    """The next request off `channel` that a consumer has to decide about, or None."""
    while True:
        request = channel.take()
        if request is None:
            return None
        if request.action == STATUS:
            channel.reply(_described())
        elif request.action == QUESTIONS:
            channel.reply(_pending_questions())
        else:
            return request


def _described() -> dict[str, object]:
    """What the run says about itself, with the describe callable's failures contained."""
    report = _watch.report
    if report is None:
        return {"attached": False}
    try:
        return report()
    except Exception as exc:  # noqa: BLE001 - a query may not be able to end the run
        logger.warning("control: describing this run failed: %s", exc)
        return {"attached": True, "error": f"{exc.__class__.__name__}: {exc}"}


def _pending_questions() -> dict[str, object]:
    """What this run is blocked asking, with the registered callable's failures contained."""
    asked = _watch.asked
    if asked is None:
        return {"ok": True, "questions": []}
    try:
        return {"ok": True, "questions": asked()}
    except Exception as exc:  # noqa: BLE001 - a query may not be able to end the run
        logger.warning("control: listing this run's questions failed: %s", exc)
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def take() -> Request | None:
    """The next request off the channel, or None."""
    return _delivered(_watch.channel)


def outstanding() -> Request | None:
    """A held request first, then the channel — what a site allowed to act on both asks."""
    held, _watch.held = _watch.held, None
    if held is not None:
        return held
    return _delivered(_watch.channel)


def hold(request: Request) -> None:
    """Put a delivered request back, for the next site that is allowed to act on it."""
    _watch.held = request


def answer(payload: dict[str, object]) -> None:
    """Reply on the armed channel to the request just taken."""
    _watch.channel.reply(payload)


def wait_until(
    predicate: Callable[[], bool] | None,
    *,
    timeout: float,
    clock: Clock,
    channel: ControlChannel = NULL_CHANNEL,
    tick: float = 1.0,
) -> Request | None:
    """Wait up to `timeout`, woken early by a control request or by `predicate`."""
    remaining = timeout
    while True:
        if predicate is not None and predicate():
            return None
        request = _delivered(channel)
        if request is not None:
            return request
        if remaining <= 0:
            return None
        slice_s = min(tick, remaining)
        fd = channel.fileno()
        if fd is None:
            clock.sleep(slice_s)
        else:
            ready, _, _ = select.select([fd], [], [], slice_s)
            if ready:
                request = _delivered(channel)
                if request is not None:
                    return request
        remaining -= slice_s


def send(run_dir: str | Path, request: Request, *, timeout: float = 5.0) -> dict[str, object]:
    """Deliver `request` to the run listening on `run_dir` and return its reply."""
    path = _socket_path(Path(run_dir))
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(path))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        client.close()
        raise FileNotFoundError(f"no run is listening on {path}") from exc
    try:
        client.sendall((request.to_json() + "\n").encode("utf-8"))
        try:
            raw = _read_message(client, limit=REPLY_LIMIT)
        except OSError:
            return {}
        if not raw:
            return {}
        try:
            reply = json.loads(raw)
        except ValueError:
            return {}
        return reply if isinstance(reply, dict) else {}
    finally:
        client.close()


def listening(run_dir: str | Path) -> bool:
    """Whether a process is serving `run_dir`'s control socket right now."""
    return _is_live(_socket_path(Path(run_dir)))


def _socket_path(run_dir: Path) -> Path:
    """Where this run's socket lives — in the run dir, unless the path is too long."""
    direct = run_dir / SOCKET_FILE
    if len(str(direct.resolve() if run_dir.exists() else direct)) <= _SUN_PATH_MAX:
        return direct
    pointer = run_dir / POINTER_FILE
    try:
        recorded = pointer.read_text(encoding="utf-8").strip()
        if recorded:
            return Path(recorded)
    except OSError:
        pass
    digest = hashlib.sha256(str(run_dir.resolve()).encode("utf-8")).hexdigest()[:16]
    chosen = Path(tempfile.gettempdir()) / f"workhorse-{digest}.sock"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        pointer.write_text(str(chosen), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - an unwritable run dir fails earlier
        logger.warning("could not record the control socket path: %s", exc)
    return chosen


def _is_live(path: Path) -> bool:
    """Whether something is actually listening on `path`, as opposed to it being litter."""
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


def _read_message(conn: socket.socket, *, limit: int) -> str:
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
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ControlProtocolError(
                f"control message exceeded {limit} bytes with no newline"
            )
    return b"".join(chunks).decode("utf-8", errors="replace")


__all__ = [
    "STOP",
    "ANSWER",
    "ControlProtocolError",
    "NULL_CHANNEL",
    "QUESTIONS",
    "STATUS",
    "POINTER_FILE",
    "SOCKET_FILE",
    "ControlChannel",
    "REPLY_LIMIT",
    "REQUEST_LIMIT",
    "FakeChannel",
    "NullChannel",
    "Request",
    "SocketChannel",
    "answer",
    "arm",
    "armed",
    "hold",
    "listening",
    "outstanding",
    "questions_with",
    "report_with",
    "send",
    "take",
    "wait_until",
]
