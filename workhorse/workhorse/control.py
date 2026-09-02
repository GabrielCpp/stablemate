"""The one channel an operator says something to a live run over.

A run in flight has to be reachable: to pick up a fix, to be told which agent CLI to use
after the old one hit a spending cap, to answer "what are you doing". Reaching it used to
mean writing a file into the run dir and waiting for something to stat it, which is a
transport that works exactly as far as the code that remembers to poll — and no further.
A run asleep in a six-day cap wait polls nothing, so it could not be reached at all.

So: one local socket, opened for the life of the process, and one wait primitive that
every waiting site in the engine goes through. The channel is a *port* rather than a
module-level global because that is what makes it substitutable — `NullChannel` for the
overwhelming majority of code that is not attached to a run (every unit test), and
`FakeChannel` for a test that wants to script a request without a socket, a thread or a
timing assumption.

What this module deliberately does **not** do is act. It delivers requests and carries a
reply back; deciding what a `reload` or a `switch-cli` means belongs to the driver and
the streaming loop, which is also what keeps this importable with no run in flight.

`Clock` is untouched by all of this. It stands in for the operating system's passage of
time, and a control message is not that; teaching `sleep` to be interrupted would make
every fake clock in the suite grow a fake message source.
"""

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

#: The one verb answered by this module rather than by a consumer of it. `status` asks
#: what the run is doing, which changes nothing about it — answering is delivery, not
#: acting — and answering it *here* is what makes it work from inside a six-day cap
#: sleep, where no consumer is looking at the channel at all.
STATUS = "status"

#: The second query verb, answered here for the same reason `status` is: "what is this
#: run blocked asking" changes nothing about the run, so no wait may end for it. What
#: the answer *is* comes from whoever registered it (`questions_with`) — this module
#: carries it, exactly as `report_with` carries the status answer.
QUESTIONS = "questions"

#: The verb that answers an operator gate. Deliberately NOT handled here: an answer
#: ends a wait, and only the waiting site knows whether its wait is the one being
#: answered — so it is delivered like a `reload`, and `pyflow`'s operator wait is the
#: one consumer that accepts it.
ANSWER = "answer"

#: The listener, in the run dir. Discovery is "look in the run dir" — see `POINTER_FILE`
#: for the one case where what is found there is a pointer rather than the socket.
SOCKET_FILE = "control.sock"

#: Written only when the run dir's own path would overflow `sun_path`. Holds the absolute
#: path of the socket that was bound instead, so discovery stays a single rule.
POINTER_FILE = "control.sock.path"

#: `sockaddr_un.sun_path` is 108 bytes including the terminator on Linux, 104 on macOS.
#: Bind fails outright above it, and a run dir nested under a workspace, a run id and a
#: sub-flow can genuinely get there — so the limit is checked rather than discovered.
_SUN_PATH_MAX = 100

#: How much is read from the socket at a time. A reply carrying a gate file is hundreds
#: of kilobytes, and 4 KiB reads made that 175 syscalls.
_CHUNK = 64 * 1024

#: What a *request* may be: a verb, a path, and an operator's prose answer. Bounded
#: because anything that can reach the socket can send one, and a peer that never sends
#: a newline must not be able to exhaust the run's memory.
REQUEST_LIMIT = 64 * 1024

#: What a *reply* may be, which is a different question with a different answer. The
#: peer here is the run this client just connected to on a 0600 socket in its own run
#: dir — not a stranger — and what it says is as big as what it was asked about: the
#: `questions` verb quotes the whole gate file, and an operator gate re-armed across a
#: long run reaches hundreds of kilobytes. Still bounded, because a wedged run must not
#: take the operator's CLI down with it, but bounded where a real payload is not.
REPLY_LIMIT = 64 * 1024 * 1024

logger = logging.getLogger(__name__)


class ControlProtocolError(Exception):
    """A message that could not be framed: over its limit with no newline in sight.

    Its own type rather than an `OSError` because it is not one — the socket worked
    perfectly, the peer said more than the reader agreed to hold. Callers distinguish
    the two: a run ignores an unframeable *request* and keeps going, while an operator
    asking a question is told, rather than handed an empty dict that reads as silence.
    """


@dataclass(frozen=True)
class Request:
    """What an operator asked for, as it arrived on the channel.

    One flat record for every verb rather than a class per action: the wire format is a
    single JSON object, the fields are few, and a union would put a match statement in
    front of every consumer to reach two booleans. `action` is what a consumer branches
    on, and an action it does not recognise is ignored rather than fatal — a newer CLI
    talking to an older run must not be able to end it.
    """

    action: str = "reload"
    core: bool = False
    at_boundary: bool = False
    cli: str = ""
    #: The named model set a `switch-profile` asks the run to resolve from next. Empty
    #: for every other verb. It is its own field rather than a second meaning for `cli`
    #: because the two are independent axes: a run can be moved onto another CLI, another
    #: profile, or both, and one string could not say which was meant.
    profile: str = ""
    #: The gate file an `answer` is for, absolute, as the sender knows it. Also carried
    #: back in replies so a client can tell *which* wait acknowledged it. Empty for the
    #: verbs that address the run rather than a gate.
    path: str = ""
    #: The operator's prose — the answer text an `answer` delivers. Its own field rather
    #: than a reuse of `cli`/`profile` because those are routing, and this is payload.
    body: str = ""
    requested_at: str = ""

    @property
    def cuts_the_turn(self) -> bool:
        """Whether this interrupts the streaming turn instead of waiting for a boundary.

        `at_boundary` is the non-default because the default reason to signal a run is
        that the turn is burning tokens on something already known to be broken. A turn
        95% through expensive work that is *not* broken is what `at_boundary` is for, and
        it is worth having to ask for.
        """
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
        """A request from a decoded JSON payload, or None when it is not one.

        Forgiving on purpose, and in one direction only: unknown keys are dropped and
        missing ones default, so an older run reads a newer CLI's message as the verb
        they share. What is rejected is a payload that is not an object at all.
        """
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
    """A source of operator requests that a `select` can wait on.

    `fileno` returning None is the whole reason this is a port and not a socket: it means
    "nothing to wait on", and it is what lets every caller keep one code path whether or
    not a run is attached. `take` is non-blocking — the caller has already decided the
    fd is ready, or is polling deliberately.
    """

    def fileno(self) -> int | None: ...

    def take(self) -> Request | None: ...

    def reply(self, payload: dict[str, object]) -> None: ...

    def close(self) -> None: ...


class NullChannel:
    """No channel at all: the default, and what every unit test gets.

    Not an error case. Most code that waits in this engine is not attached to a run —
    a test driving the ladder, a workflow executed in-process — and it must wait exactly
    as it did before this module existed. `fileno() is None` is what guarantees that:
    `wait_until` never reaches `select`, so the wait goes through the injected clock and
    every existing `FakeClock.slept` assertion still holds.
    """

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
    """A `AF_UNIX` listener in the run dir, accepted from the caller's own `select`.

    One connection carries one request and one reply, then closes. There is no session
    and no concurrency: the operator's CLI connects, writes a line, reads a line, exits.
    Accepting from inside the caller's `select` rather than from a thread is deliberate —
    the streaming loop is already a select loop, and a background thread delivering
    requests into it would need a queue and a wake-up pipe to end up where the fd already
    is.
    """

    def __init__(self, path: Path, listener: socket.socket) -> None:
        self.path = path
        self._listener = listener
        self._conn: socket.socket | None = None

    @classmethod
    def open(cls, run_dir: str | Path) -> "SocketChannel":
        """Bind the channel for `run_dir`, replacing a socket no one is listening on.

        A run killed with SIGKILL leaves its socket file behind, and the next run in the
        same dir must not be unreachable because of it. A refused connect proves nobody
        is on the other end, which makes the unlink safe; a connect that *succeeds* means
        a second process is already serving this run dir, and that is a hard error rather
        than something to stomp on — two runs sharing a run dir is the bug, not the
        socket.
        """
        directory = Path(run_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = _socket_path(directory)
        if path.exists():
            if _is_live(path):
                raise OSError(f"another run is already listening on {path}")
            path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        # The run dir is already the trust boundary; the socket inherits it rather than
        # widening it to anyone who can reach the path.
        os.chmod(path, 0o600)
        listener.listen(1)
        listener.setblocking(False)
        return cls(path, listener)

    def fileno(self) -> int | None:
        return self._listener.fileno()

    def take(self) -> Request | None:
        """Accept a waiting connection and read its one request, or None.

        Never raises. This runs inside a live agent turn's streaming loop, and a
        malformed message, a client that connected and vanished, or a socket error must
        not be the thing that ends an unattended run — the worst outcome of a bad message
        is that it is ignored.
        """
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
        """Answer the request just taken, if its connection is still there.

        A reply is best-effort by design: `control reload` does not wait for one, so the
        common case is a client that has already gone. What must not happen is the run
        dying because the operator pressed ctrl-c.
        """
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
    """Scripted requests, for a test that wants the behaviour and not the socket.

    `fileno` is None, so a test using this exercises the same code path a real run takes
    only up to the point where `select` would be involved — which is the point: what a
    test asserts on is that a waiting site *stops* when a request arrives, not that a
    kernel delivered it. `replies` records what the site answered.
    """

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
    """The channel this process's run is reachable on, set once when the run starts.

    Process-wide because there is one run per process and the streaming loop is several
    layers below anything that knows where the run's artifacts live — the same reason
    `runner/process.py` holds one module-level `ProcessSupervisor`. It is the *installed
    instance* that is global, never the port: every consumer still takes a
    `ControlChannel`, which is what keeps `NullChannel` and `FakeChannel` substitutable.

    `held` is a request that was delivered but deliberately not acted on yet — an
    `--at-boundary` reload arriving mid-turn. Taking it off the socket consumes it, so
    something has to remember it until the state boundary that honours it.

    `report` is how the process describes itself to a `status` request. A callable rather
    than a dict because the answer must be the run's position *now*, and the point of
    asking is usually that the run has been somewhere for a suspiciously long time.

    `asked` is the same shape for the `questions` verb: what this run is blocked asking
    an operator, right now. Registered by the waiting site on entry and cleared on exit,
    and a callable for the same reason `report` is — the gate file is the authoritative
    copy of the question, so the answer worth giving re-reads it at the moment of asking.
    """

    channel: ControlChannel = NULL_CHANNEL
    held: Request | None = None
    report: Callable[[], dict[str, object]] | None = None
    asked: Callable[[], list[dict[str, object]]] | None = None


_watch = _Watch()


def arm(channel: ControlChannel | None) -> None:
    """Make `channel` the one this process answers on. `None` disarms.

    Disarming forgets the reporter too: a process with no channel is not a run, and a
    stale reporter would describe the previous one to whoever asked next.
    """
    _watch.channel = channel or NULL_CHANNEL
    _watch.held = None
    if channel is None:
        _watch.report = None
        _watch.asked = None


def report_with(describe: Callable[[], dict[str, object]] | None) -> None:
    """Say how this process answers `status`. `None` restores the unattached answer."""
    _watch.report = describe


def questions_with(pending: Callable[[], list[dict[str, object]]] | None) -> None:
    """Say what this run is blocked asking an operator. `None` means: nothing.

    Registered by the operator wait on entry and cleared on exit, so the `questions`
    verb answers an empty list everywhere else — a run that is working has no pending
    question, and saying so is the answer, not an error.
    """
    _watch.asked = pending


def armed() -> ControlChannel:
    """The installed channel — `NULL_CHANNEL` when no run is attached.

    What the waiting sites deep in the runner pass to `wait_until`. With nothing armed it
    is an attribute read returning a channel whose `fileno()` is None, so an unarmed
    process — every unit test that streams a fake agent — pays nothing.
    """
    return _watch.channel


def _delivered(channel: ControlChannel) -> Request | None:
    """The next request off `channel` that a consumer has to decide about, or None.

    The query verbs never get that far: `status` and `questions` are answered here, on
    the connection each arrived on, and the take is repeated. That is deliberately not a
    convenience — every consumer in the engine is a *waiting* site with a policy about
    what may end its wait, and a query that ends a cap wait to be told "still capped" is
    the wait answering the wrong question. Answering below them means both queries work
    from every wait there is, including the six-day one, without any of them knowing the
    verbs exist.
    """
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
    """What the run says about itself, with the describe callable's failures contained.

    The callable belongs to whoever armed the watch and is invoked from *inside* the
    streaming loop, which is the deepest, longest-lived frame there is. An exception
    escaping here would therefore not fail a query — it would end the run, from a verb
    whose whole premise is that asking changes nothing. Live proof, and the reason for the
    guard: a describe closure that referenced a name its own module did not yet define
    took a multi-hour run down the moment it was first asked where it was.
    """
    report = _watch.report
    if report is None:
        return {"attached": False}
    try:
        return report()
    except Exception as exc:  # noqa: BLE001 - a query may not be able to end the run
        logger.warning("control: describing this run failed: %s", exc)
        return {"attached": True, "error": f"{exc.__class__.__name__}: {exc}"}


def _pending_questions() -> dict[str, object]:
    """What this run is blocked asking, with the registered callable's failures contained.

    Same containment as `_described`, for the same reason: this runs inside whatever wait
    the request landed under, and a query may not be able to end the run. An empty list
    is the well-formed answer for a run that is not blocked — a poller reads it as "no
    gate here", which is exactly the reconcile it came for.
    """
    asked = _watch.asked
    if asked is None:
        return {"ok": True, "questions": []}
    try:
        return {"ok": True, "questions": asked()}
    except Exception as exc:  # noqa: BLE001 - a query may not be able to end the run
        logger.warning("control: listing this run's questions failed: %s", exc)
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def take() -> Request | None:
    """The next request off the channel, or None. A held request is *not* returned here.

    Deliberately blind to `hold`: the site that declined a request and put it back is the
    streaming loop, which asks again on its very next slice. Handing it back its own
    declined request would acknowledge the same message once per second for the rest of
    the turn — and never honour it, since declining is exactly what that site does.
    """
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
    """Wait up to `timeout`, woken early by a control request or by `predicate`.

    The single waiting primitive in the engine, and it has two arms on purpose. The
    channel makes a wait *prompt*: an operator's message lands within a select slice
    rather than at the end of a six-day cap window. `predicate` makes it *authoritative*:
    the operator gate's answer is a file a human edits, and re-reading it on a slow tick
    is what makes the wait correct even when no message is ever sent. Both wake the same
    line of code, so neither is a fallback bolted onto the other.

    Returns the request that ended the wait, or None when the predicate or the timeout
    did. A predicate is checked *before* waiting, so a condition that is already true
    costs nothing.
    """
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
            # Nothing to select on, so time is the only thing that can end this wait —
            # and it passes through the injected clock, exactly as it did before there
            # was a channel at all.
            clock.sleep(slice_s)
        else:
            ready, _, _ = select.select([fd], [], [], slice_s)
            if ready:
                request = _delivered(channel)
                if request is not None:
                    return request
        remaining -= slice_s


def send(run_dir: str | Path, request: Request, *, timeout: float = 5.0) -> dict[str, object]:
    """Deliver `request` to the run listening on `run_dir` and return its reply.

    Raises `FileNotFoundError` when nothing is listening, which is the honest answer:
    unlike a request file, a channel only exists while the run does, so "the run is not
    running" is reported at the moment of asking rather than by a message nobody reads.

    Raises `ControlProtocolError` when the run answered with more than `REPLY_LIMIT`.
    Every other failure here — a timeout, a reply that is not JSON — returns `{}`, and
    that conflation is deliberate: they all mean "no usable answer, the file-derived
    view decides". An oversized reply must *not* join them, because it is the one case
    where the run answered correctly and the transport lost it; returning `{}` for it
    is indistinguishable from a run that said nothing, and a poller that cannot tell
    those apart reports a parked run as healthy.
    """
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


def _socket_path(run_dir: Path) -> Path:
    """Where this run's socket lives — in the run dir, unless the path is too long.

    `sun_path` is a fixed ~108-byte field, and a run dir under a workspace path, a run id
    and a sub-flow can exceed it; binding would then fail for a reason that has nothing to
    do with the run. So an over-long dir gets a socket in the temp dir keyed by a digest
    of its path, and a pointer file in the run dir naming it. Discovery stays one rule —
    look in the run dir — because the pointer is read from there too.
    """
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
    """One newline-terminated message, reassembled across however many packets it
    arrives in.

    A stream socket delivers bytes, not messages, so the newline is the frame and this
    loop is what turns a stream back into one. `limit` bounds what may be buffered
    before that frame closes, because a peer that never sends a newline is otherwise an
    unbounded allocation.

    **Exceeding it raises.** This used to `break` out of the loop and return the bytes
    read so far, which is the one outcome that cannot be right: a prefix of a JSON
    object is not a shorter message, it is a corrupt one, and the caller had no way to
    tell it from a peer that answered nothing. That is how a 698 KB `questions` reply
    reached groom as `{}`, and left a run parked 20 hours on an operator gate the
    dashboard showed no question for.
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
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ControlProtocolError(
                f"control message exceeded {limit} bytes with no newline"
            )
    return b"".join(chunks).decode("utf-8", errors="replace")


__all__ = [
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
    "outstanding",
    "questions_with",
    "report_with",
    "send",
    "take",
    "wait_until",
]
