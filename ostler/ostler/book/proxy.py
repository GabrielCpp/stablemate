"""A recording reverse proxy: it stands where an app sends its requests, forwards every byte to the service the
request is for, and keeps each HTTP/1.1 exchange it saw go by. A phone sees no request of its own, so a book reads
the app's own call, and the answer it got, from here. A plain HTTP target needs no certificate and no change to the
app.

A reader waits on a condition the proxy signals when an exchange completes. No wait is on a clock."""

from __future__ import annotations

import gzip
import json
import re
import shutil
import socket
import subprocess
import threading
import zlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from ostler.book.errors import BookError

HEAD_END = b"\r\n\r\n"
NO_BODY = {204, 304}


@dataclass
class Exchange:
    """One request and the answer it got. `framed` is False when the body could not be framed, and `body` then holds
    the bytes as they crossed the proxy."""

    seq: int
    method: str
    url: str
    status: int
    headers: list[tuple[str, str]]
    body: bytes
    framed: bool = True

    def header(self, name: str) -> str:
        return next((value for key, value in self.headers if key.lower() == name.lower()), "")

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class Head:
    first: str
    headers: list[tuple[str, str]]

    def header(self, name: str) -> str:
        return next((value for key, value in self.headers if key.lower() == name.lower()), "")


@dataclass
class Message:
    head: Head
    body: bytes
    framed: bool
    asked: tuple[str, str] = ("", "")


def split_head(data: bytes) -> tuple[Head, int] | None:
    end = data.find(HEAD_END)
    if end < 0:
        return None
    lines = data[:end].decode("latin-1").split("\r\n")
    headers = [(key.strip(), value.strip()) for key, _, value in (line.partition(":") for line in lines[1:])]
    return Head(lines[0], headers), end + len(HEAD_END)


def unchunk(data: bytes) -> tuple[bytes, int] | None:
    """The decoded body of a chunked message at the start of `data` and the bytes it took, None while it is incomplete,
    ValueError when it is not chunked."""
    at = 0
    body = b""
    while True:
        line_end = data.find(b"\r\n", at)
        if line_end < 0:
            return None
        size_text = data[at:line_end].split(b";")[0].strip()
        try:
            size = int(size_text, 16)
        except ValueError:
            raise ValueError(f"bad chunk size {size_text!r}") from None
        at = line_end + 2
        if size == 0:
            while True:
                line_end = data.find(b"\r\n", at)
                if line_end < 0:
                    return None
                if line_end == at:
                    return body, at + 2
                at = line_end + 2
        if len(data) < at + size + 2:
            return None
        body += data[at:at + size]
        at += size + 2


def decoded(head: Head, body: bytes) -> bytes:
    coding = head.header("content-encoding").lower()
    try:
        if coding == "gzip":
            return gzip.decompress(body)
        if coding == "deflate":
            return zlib.decompress(body)
    except (OSError, zlib.error):
        return body
    return body


class Stream:
    """The messages of one direction of one connection, framed as the bytes arrive. `asked` is the method of the
    request an answer is for, so a stream of answers needs it to know that a HEAD answer has no body."""

    def __init__(self, answers: bool, takes: Callable[[], tuple[str, str]] | None = None):
        self.answers = answers
        self.takes = takes
        self.buffer = b""
        self.head: Head | None = None
        self.method = ""
        self.asked = ("", "")
        self.raw = False
        self.messages: list[Message] = []

    def feed(self, data: bytes) -> list[Message]:
        self.buffer += data
        self.messages = []
        while self.buffer and not self.raw and self.step():
            pass
        return self.messages

    def finish(self) -> list[Message]:
        """The connection ended on this side: a body that runs to the end is complete."""
        self.messages = []
        if self.head is not None and self.until_close():
            self.emit(self.head, self.buffer, True)
        elif self.head is not None:
            self.emit(self.head, self.buffer, False)
        self.head = None
        self.buffer = b""
        return self.messages

    def until_close(self) -> bool:
        assert self.head is not None
        return self.answers and not self.head.header("content-length") and "chunked" not in self.head.header("transfer-encoding").lower()

    def emit(self, head: Head, body: bytes, framed: bool) -> None:
        self.messages.append(Message(head, body if not framed else decoded(head, body), framed, self.asked))

    def step(self) -> bool:
        if self.head is None:
            found = split_head(self.buffer)
            if found is None:
                return False
            self.head, used = found
            self.buffer = self.buffer[used:]
            parts = self.head.first.split()
            status = int(parts[1]) if self.answers and len(parts) > 1 and parts[1].isdigit() else 0
            if self.answers and 100 <= status < 200 and status != 101:
                self.head = None
                return True
            if self.answers and self.takes is not None:
                self.asked = self.takes()
                self.method = self.asked[0]
            if status == 101:
                self.emit(self.head, b"", False)
                self.head = None
                self.raw = True
                return False
        head = self.head
        assert head is not None
        parts = head.first.split()
        status = int(parts[1]) if self.answers and len(parts) > 1 and parts[1].isdigit() else 0
        if self.answers and (self.method == "HEAD" or status in NO_BODY):
            self.emit(head, b"", True)
            self.head = None
            return True
        if "chunked" in head.header("transfer-encoding").lower():
            try:
                found_body = unchunk(self.buffer)
            except ValueError:
                self.emit(head, self.buffer, False)
                self.head = None
                self.raw = True
                return False
            if found_body is None:
                return False
            body, used = found_body
            self.buffer = self.buffer[used:]
            self.emit(head, body, True)
            self.head = None
            return True
        length = head.header("content-length")
        if length:
            if not length.isdigit():
                self.emit(head, self.buffer, False)
                self.head = None
                self.raw = True
                return False
            size = int(length)
            if len(self.buffer) < size:
                return False
            body, self.buffer = self.buffer[:size], self.buffer[size:]
            self.emit(head, body, True)
            self.head = None
            return True
        if self.answers:
            return False
        self.emit(head, b"", True)
        self.head = None
        return True


class Recording:
    """The exchanges seen, in order, and the condition a reader waits on."""

    def __init__(self) -> None:
        self.exchanges: list[Exchange] = []
        self.landed = threading.Condition()

    def add(self, answer: Message) -> None:
        method, url = answer.asked
        with self.landed:
            parts = answer.head.first.split()
            status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            self.exchanges.append(Exchange(len(self.exchanges), method, url, status, answer.head.headers, answer.body, answer.framed))
            self.landed.notify_all()

    def mark(self) -> int:
        """The sequence number the next exchange will get."""
        with self.landed:
            return len(self.exchanges)

    def since(self, mark: int) -> list[Exchange]:
        with self.landed:
            return list(self.exchanges[mark:])

    def first(self, mark: int, wanted: Callable[[Exchange], bool]) -> Exchange | None:
        with self.landed:
            return next((seen for seen in self.exchanges[mark:] if wanted(seen)), None)

    def last(self, mark: int, wanted: Callable[[Exchange], bool]) -> Exchange | None:
        """The latest exchange before `mark` that `wanted` accepts."""
        with self.landed:
            return next((seen for seen in reversed(self.exchanges[:mark]) if wanted(seen)), None)

    def wait(self, mark: int, wanted: Callable[[Exchange], bool], timeout: float | None = None) -> Exchange | None:
        """The first exchange from `mark` on that `wanted` accepts, once it has landed. None when `timeout` seconds
        pass first, or at once for 0."""
        found: list[Exchange] = []

        def landed() -> bool:
            seen = next((one for one in self.exchanges[mark:] if wanted(one)), None)
            if seen is not None:
                found.append(seen)
            return seen is not None

        with self.landed:
            self.landed.wait_for(landed, timeout)
        return found[0] if found else None


def holder_of(port: int) -> str:
    """The process that listens on `port`, as `ss` names it, or ''."""
    ss = shutil.which("ss")
    if ss is None:
        return ""
    try:
        listing = subprocess.run([ss, "-ltnpH", f"sport = :{port}"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return ""
    found = re.search(r'users:\(\("([^"]+)",pid=(\d+)', listing)
    return f"{found.group(1)} (pid {found.group(2)})" if found else ""


@dataclass
class Proxy:
    """Listens on `port` of this host and forwards to `target`, a `(host, port)` pair."""

    port: int
    target: tuple[str, int]
    recording: Recording = field(default_factory=Recording)
    server: socket.socket | None = None
    closing: threading.Event = field(default_factory=threading.Event)
    live: set[socket.socket] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None

    def start(self) -> "Proxy":
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", self.port))
        except OSError as refused:
            listener.close()
            held = holder_of(self.port)
            by = f" by {held}" if held else ""
            raise BookError(f"the port {self.port} the app sends its requests to is already held{by}: {refused}") from None
        listener.listen(64)
        self.server = listener
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.closing.set()
        if self.server is not None:
            try:
                self.server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.server.close()
        with self.lock:
            for held in list(self.live):
                try:
                    held.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                held.close()
            self.live.clear()
        if self.thread is not None:
            self.thread.join()

    def accept(self) -> None:
        assert self.server is not None
        while not self.closing.is_set():
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(client,), daemon=True).start()

    def serve(self, client: socket.socket) -> None:
        try:
            upstream = socket.create_connection(self.target)
        except OSError:
            client.close()
            return
        with self.lock:
            self.live.update((client, upstream))
        asked: deque[tuple[str, str]] = deque()
        requests = Stream(False)
        answers = Stream(True, lambda: asked.popleft() if asked else ("", ""))

        def forward_requests(data: bytes) -> None:
            for message in requests.feed(data):
                parts = message.head.first.split()
                asked.append((parts[0] if parts else "", parts[1] if len(parts) > 1 else ""))

        def forward_answers(data: bytes) -> None:
            self.answered(answers.feed(data))

        up = threading.Thread(target=self.pump, args=(client, upstream, forward_requests, lambda: requests.finish()), daemon=True)
        up.start()
        self.pump(upstream, client, forward_answers, lambda: self.answered(answers.finish()))
        up.join()
        for held in (client, upstream):
            with self.lock:
                self.live.discard(held)
            held.close()

    def answered(self, messages: list[Message]) -> None:
        for message in messages:
            self.recording.add(message)

    def pump(self, source: socket.socket, sink: socket.socket, observe: Callable[[bytes], Any], ended: Callable[[], Any]) -> None:
        while True:
            try:
                data = source.recv(65536)
            except OSError:
                data = b""
            if not data:
                break
            observe(data)
            try:
                sink.sendall(data)
            except OSError:
                break
        ended()
        try:
            sink.shutdown(socket.SHUT_WR)
        except OSError:
            pass
