"""The gRPC client of a scenario: the call it makes, the reply it gets, and the callers that make the call."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

CODE_NAMES = (
    "OK", "CANCELLED", "UNKNOWN", "INVALID_ARGUMENT", "DEADLINE_EXCEEDED", "NOT_FOUND", "ALREADY_EXISTS",
    "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "ABORTED", "OUT_OF_RANGE",
    "UNIMPLEMENTED", "INTERNAL", "UNAVAILABLE", "DATA_LOSS", "UNAUTHENTICATED",
)
SCHEME = "grpc://"
DEFAULT_DEADLINE = 30.0
STREAM_SETTLE_S = 2.0
DEFAULT_WINDOW_S = 10.0
_GRACE_S = 5.0
_EXCERPT_CHARS = 300
_REDACTED = "[redacted]"


class GrpcError(RuntimeError):
    """A call whose status the scenario did not say it expected, or that never reached the server, and whether the scenario already recorded it as a failed check."""

    def __init__(self, message: str, *, recorded: bool = False) -> None:
        super().__init__(message)
        self.recorded = recorded


@dataclass(frozen=True)
class Call:
    """One unary or server-streaming call: where, which method, the request message and the metadata it carries."""

    address: str
    method: str
    request: object = None
    metadata: tuple[tuple[str, str], ...] = ()
    deadline: float = DEFAULT_DEADLINE


@dataclass(frozen=True)
class Reply:
    """What a call answered: the status name, its message, and the reply messages as JSON."""

    status: str
    message: str = ""
    messages: tuple[object, ...] = ()
    streamed: bool = False

    @property
    def text(self) -> str:
        return json.dumps(list(self.messages)) if self.messages else self.message

    def json(self) -> object:
        """The one reply message, or the list of them when a stream sent several. A server stream always answers the list."""
        if self.streamed:
            return list(self.messages)
        if not self.messages:
            raise ValueError(f"the call replied {self.status} with no message: {self.message[:200]!r}")
        return self.messages[0] if len(self.messages) == 1 else list(self.messages)


class OpenStream(Protocol):
    def close(self) -> Reply: ...


class Caller(Protocol):
    def call(self, call: Call) -> Reply: ...

    def open(self, call: Call, window: float) -> OpenStream: ...


def _body(request: object) -> str:
    return json.dumps({} if request is None else request)


def _scrubbed(text: str, call: Call) -> str:
    for _name, value in call.metadata:
        if value:
            text = text.replace(value, _REDACTED)
    return text


def _messages(stdout: str) -> tuple[object, ...]:
    decoder = json.JSONDecoder()
    found: list[object] = []
    at = 0
    while at < len(stdout):
        if stdout[at].isspace():
            at += 1
            continue
        message, at = decoder.raw_decode(stdout, at)
        found.append(message)
    return tuple(found)


def _scrubbed_json(value: object, call: Call) -> object:
    if isinstance(value, str):
        return _scrubbed(value, call)
    if isinstance(value, list):
        return [_scrubbed_json(item, call) for item in value]
    if isinstance(value, dict):
        return {_scrubbed(str(key), call): _scrubbed_json(item, call) for key, item in value.items()}
    return value


def _status_of(stderr: str) -> tuple[str, str] | None:
    start = stderr.find("{")
    if start < 0:
        return None
    try:
        status, _ = json.JSONDecoder().raw_decode(stderr, start)
    except json.JSONDecodeError:
        return None
    code = status.get("code") if isinstance(status, dict) else None
    if isinstance(code, bool) or not isinstance(code, int) or not 0 < code < len(CODE_NAMES):
        return None
    message = status.get("message", "")
    return CODE_NAMES[code], message if isinstance(message, str) else ""


class GrpcurlCaller:
    """Makes the call with the grpcurl binary, the request on stdin, and maps what it printed to a reply."""

    def __init__(self, command: str) -> None:
        self._command = command

    def argv(self, call: Call) -> list[str]:
        headers = [part for name, value in call.metadata for part in ("-H", f"{name}: {value}")]
        return [
            self._command, "-plaintext", "-format-error", "-d", "@", *headers,
            "-max-time", str(call.deadline), call.address, call.method,
        ]

    def call(self, call: Call) -> Reply:
        where = f"{call.method} on {call.address}"
        try:
            done = subprocess.run(  # noqa: S603 - argv built from a config-declared command
                self.argv(call), input=_body(call.request), capture_output=True, text=True,
                timeout=call.deadline + _GRACE_S, check=False,
            )
        except FileNotFoundError as exc:
            raise GrpcError(f"{where} could not run: grpcurl command {self._command!r} is not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise GrpcError(f"{where} did not return within {call.deadline}s") from exc
        if done.returncode == 0:
            try:
                return Reply("OK", "", _messages(done.stdout))
            except json.JSONDecodeError as exc:
                raise GrpcError(f"{where} printed a reply that is not JSON") from exc
        status = _status_of(done.stderr)
        if status is None:
            seen = _scrubbed(done.stderr.strip(), call)[:_EXCERPT_CHARS]
            raise GrpcError(f"{where} could not be called, grpcurl exited {done.returncode}: {seen}")
        return Reply(status[0], _scrubbed(status[1], call))

    def open(self, call: Call, window: float) -> OpenStream:
        where = f"{call.method} on {call.address}"
        try:
            process = subprocess.Popen(  # noqa: S603 - argv built from a config-declared command
                self.argv(replace(call, deadline=window)), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
        except FileNotFoundError as exc:
            raise GrpcError(f"{where} could not run: grpcurl command {self._command!r} is not on PATH") from exc
        try:
            sent = process.stdin
            if sent is None:
                raise GrpcError(f"{where} has no stdin to send its request on")
            sent.write(_body(call.request))
            sent.close()
            process.stdin = None
        except BaseException:
            process.kill()
            process.wait()
            raise
        return _GrpcurlStream(process, call, window, where)


class _GrpcurlStream:
    """A grpcurl process listening to a server stream until its window closes."""

    def __init__(self, process: subprocess.Popen[str], call: Call, window: float, where: str) -> None:
        self._process = process
        self._call = call
        self._window = window
        self._where = where

    def close(self) -> Reply:
        try:
            stdout, stderr = self._process.communicate(timeout=self._window + _GRACE_S)
        except subprocess.TimeoutExpired as exc:
            raise GrpcError(f"{self._where} did not stop within {self._window}s") from exc
        finally:
            if self._process.poll() is None:
                self._process.kill()
                self._process.wait()
        try:
            messages = tuple(_scrubbed_json(message, self._call) for message in _messages(stdout))
        except json.JSONDecodeError as exc:
            raise GrpcError(f"{self._where} printed a reply that is not JSON") from exc
        if self._process.returncode == 0:
            return Reply("OK", "", messages, streamed=True)
        status = _status_of(stderr)
        if status is None:
            seen = _scrubbed(stderr.strip(), self._call)[:_EXCERPT_CHARS]
            raise GrpcError(f"{self._where} could not be called, grpcurl exited {self._process.returncode}: {seen}")
        if status[0] == "DEADLINE_EXCEEDED":
            return Reply("OK", "", messages, streamed=True)
        return Reply(status[0], _scrubbed(status[1], self._call), messages, streamed=True)


class RecordedCaller:
    """Answers from a table keyed by method and request, and remembers every call it was handed."""

    def __init__(self, replies: Mapping[tuple[str, str], Reply]) -> None:
        self._replies = dict(replies)
        self.calls: list[Call] = []
        self.events: list[tuple[str, str]] = []

    @staticmethod
    def key(method: str, request: object) -> tuple[str, str]:
        return method, json.dumps({} if request is None else request, sort_keys=True)

    def call(self, call: Call) -> Reply:
        self.calls.append(call)
        self.events.append(("call", call.method))
        return self._answer(call)

    def open(self, call: Call, window: float) -> OpenStream:
        self.calls.append(call)
        self.events.append(("open", call.method))
        return _RecordedStream(self, call, self._answer(call))

    def _answer(self, call: Call) -> Reply:
        reply = self._replies.get(self.key(call.method, call.request))
        if reply is None:
            raise GrpcError(f"no recorded reply for {call.method} with {_body(call.request)}")
        return reply


class _RecordedStream:
    def __init__(self, caller: RecordedCaller, call: Call, reply: Reply) -> None:
        self._caller = caller
        self._call = call
        self._reply = reply

    def close(self) -> Reply:
        self._caller.events.append(("close", self._call.method))
        return replace(self._reply, streamed=True)


def _allowed(expect_status: str | Sequence[str] | None) -> set[str] | None:
    if expect_status is None:
        return None
    if isinstance(expect_status, str):
        return {expect_status.upper()}
    return {name.upper() for name in expect_status}


class Grpc:
    """A small gRPC client bound to a target's address."""

    def __init__(
        self,
        address: str | None,
        caller_for: Callable[[], Caller],
        *,
        deadline: float = DEFAULT_DEADLINE,
        on_unexpected_status: Callable[[str, str, str, Sequence[str], str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        text = (address or "").strip()
        self.address = text.removeprefix(SCHEME).rstrip("/")
        self.deadline = deadline
        self._caller_for = caller_for
        self._on_unexpected_status = on_unexpected_status
        self._sleep = sleep
        self.metadata: dict[str, str] = {}

    def call(
        self,
        method: str,
        request: object = None,
        *,
        metadata: Mapping[str, str] | None = None,
        expect_status: str | Sequence[str] | None = None,
        deadline: float | None = None,
    ) -> Reply:
        merged = self._merged(method, metadata)
        reply = self._caller_for().call(
            Call(self.address, method, request, tuple(merged.items()), deadline or self.deadline)
        )
        return self._judged(method, reply, expect_status)

    def stream(
        self,
        method: str,
        request: object = None,
        *,
        during: tuple[str, object] | None = None,
        metadata: Mapping[str, str] | None = None,
        expect_status: str | Sequence[str] | None = None,
        window: float | None = None,
        settle: float | None = None,
    ) -> Reply:
        merged = self._merged(method, metadata)
        listened = DEFAULT_WINDOW_S if window is None else window
        opened = self._caller_for().open(
            Call(self.address, method, request, tuple(merged.items()), listened), listened
        )
        try:
            if during is not None:
                self._sleep(STREAM_SETTLE_S if settle is None else settle)
                self.call(during[0], during[1], metadata=merged)
        finally:
            reply = opened.close()
        return self._judged(method, reply, expect_status)

    def _merged(self, method: str, metadata: Mapping[str, str] | None) -> dict[str, str]:
        if not self.address:
            raise ValueError(
                f"{method!r} needs an address but the target declares no base_url; "
                "set base_url=\"grpc://host:port\" on the target"
            )
        return {**self.metadata, **(metadata or {})}

    def _judged(self, method: str, reply: Reply, expect_status: str | Sequence[str] | None) -> Reply:
        allowed = _allowed(expect_status)
        if allowed is None:
            if reply.status != "OK":
                raise GrpcError(f"{method} on {self.address} replied {reply.status}: {reply.message[:500]}")
        elif reply.status not in allowed:
            if self._on_unexpected_status is not None:
                self._on_unexpected_status(method, self.address, reply.status, sorted(allowed), reply.message)
            raise GrpcError(
                f"{method} on {self.address} replied {reply.status}, expected {sorted(allowed)}: "
                f"{reply.message[:500]}",
                recorded=self._on_unexpected_status is not None,
            )
        return reply


__all__ = [
    "CODE_NAMES", "DEFAULT_WINDOW_S", "STREAM_SETTLE_S", "Call", "Caller", "Grpc", "GrpcError", "GrpcurlCaller",
    "OpenStream", "RecordedCaller", "Reply",
]
