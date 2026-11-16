"""The recording proxy, and a phone list read from the request the app itself sent through it."""

from __future__ import annotations

import http.client
import json
import socket
import socketserver
import threading
from typing import Any, Iterator

import pytest

from ostler.book import BookError, Device, Environment, MobileSurface, Screen, T, request
from ostler.book.proxy import Proxy
from ostler.book.screen import Lists, Select
from book_todo import module
from test_book_phone_lists import add, phone, titles

CHUNKED = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n"
           b"5\r\n[\"a\",\r\n6\r\n\"b\"]  \r\n0\r\n\r\n")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Upstream(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture
def upstream() -> Iterator[tuple[int, list[bytes]]]:
    seen: list[bytes] = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                while self.rfile.readline() not in (b"\r\n", b""):
                    pass
                seen.append(line)
                if b"/chunked" in line:
                    self.wfile.write(CHUNKED)
                    continue
                body = json.dumps({"path": line.split()[1].decode()}).encode()
                self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body)

    server = Upstream(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], seen
    server.shutdown()
    server.server_close()


@pytest.fixture
def proxy(upstream: tuple[int, list[bytes]]) -> Iterator[Proxy]:
    held = Proxy(free_port(), ("127.0.0.1", upstream[0])).start()
    yield held
    held.stop()


def get(port: int, *paths: str) -> list[bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port)
    bodies = []
    for path in paths:
        connection.request("GET", path, headers={"Authorization": "Bearer test-token"})
        bodies.append(connection.getresponse().read())
    connection.close()
    return bodies


def test_two_exchanges_on_one_keep_alive_connection_are_recorded_with_their_bodies_in_order(proxy: Proxy) -> None:
    assert get(proxy.port, "/v1/one?x=1", "/v1/two") == [b'{"path": "/v1/one?x=1"}', b'{"path": "/v1/two"}']

    first, second = proxy.recording.since(0)
    assert (first.seq, first.method, first.url, first.status, first.json()) == (0, "GET", "/v1/one?x=1", 200, {"path": "/v1/one?x=1"})
    assert (second.seq, second.url, second.json()) == (1, "/v1/two", {"path": "/v1/two"})
    assert first.header("content-type") == "application/json"


def test_a_chunked_answer_is_decoded(proxy: Proxy) -> None:
    assert get(proxy.port, "/chunked") == [b'["a","b"]  ']

    [seen] = proxy.recording.since(0)
    assert seen.framed
    assert seen.body == b'["a","b"]  '


def test_an_answer_that_cannot_be_framed_is_left_as_raw_bytes_and_says_so() -> None:
    from ostler.book.proxy import Stream

    stream = Stream(True, lambda: ("GET", "/x"))

    [message] = stream.feed(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\nraw")

    assert not message.framed
    assert message.body == b"zz\r\nraw"


def test_two_concurrent_connections_are_both_recorded(proxy: Proxy) -> None:
    ready = threading.Barrier(2)

    def call(path: str) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", proxy.port)
        connection.connect()
        ready.wait()
        connection.request("GET", path)
        connection.getresponse().read()
        connection.close()

    threads = [threading.Thread(target=call, args=(path,)) for path in ("/v1/a", "/v1/b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(seen.url for seen in proxy.recording.since(0)) == ["/v1/a", "/v1/b"]


def test_a_reader_waiting_for_the_next_exchange_returns_when_it_lands(proxy: Proxy) -> None:
    mark = proxy.recording.mark()
    found: list[Any] = []
    waiting = threading.Thread(target=lambda: found.append(proxy.recording.wait(mark, lambda seen: seen.url == "/v1/later")))
    waiting.start()

    get(proxy.port, "/v1/earlier", "/v1/later")

    waiting.join(30)
    assert not waiting.is_alive()
    assert found[0].url == "/v1/later"
    assert found[0].seq == mark + 1


def test_a_port_already_held_is_refused_naming_it() -> None:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]

        with pytest.raises(BookError, match=rf"the port {port} the app sends its requests to is already held"):
            Proxy(port, ("127.0.0.1", 1)).start()


class Items(Screen):
    who = Select("who", T(en="Who", fr="Qui"), lists=Lists(head=("Anyone",), given=request("GET", "/todos"), derived=titles))


@pytest.fixture
def served() -> Iterator[Any]:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


def app(environment: Environment, port: int) -> MobileSurface:
    class App(MobileSurface):
        app_id = "com.example.app"
        listens = {port: "api"}
        timeout = 10.0

        def open(self) -> None:
            return None

        def restore(self) -> None:
            return None

    return App(environment, (Items,))


def test_a_phone_list_declared_with_request_is_judged_from_the_body_the_app_received(monkeypatch, served) -> None:
    server = served
    add(server, "first")
    add(server, "second")
    monkeypatch.setattr(Device, "start", lambda self: None)
    shown, calls = phone(monkeypatch, Items, "Anyone", "second", "first")
    port = free_port()
    surface = app(Environment("local", {"api": server.url}), port)
    surface.browser = shown
    surface.start()
    try:
        surface.stepping()
        get(port, "/todos")
        shown.fill(Items.who, "first")
        assert shown.list_faults() == []
    finally:
        surface.stop()


def test_a_planted_extra_row_turns_a_proxy_fed_phone_list_red(monkeypatch, served) -> None:
    server = served
    add(server, "first")
    monkeypatch.setattr(Device, "start", lambda self: None)
    shown, calls = phone(monkeypatch, Items, "Anyone", "first", "planted")
    port = free_port()
    surface = app(Environment("local", {"api": server.url}), port)
    surface.browser = shown
    surface.start()
    try:
        surface.stepping()
        get(port, "/todos")
        shown.fill(Items.who, "first")
        assert shown.list_faults() == ["the list Items.who shows ['Anyone', 'first', 'planted'], the book derives ['Anyone', 'first']"]
    finally:
        surface.stop()


def test_a_list_judged_in_a_later_step_reads_the_last_matching_request_before_the_mark(monkeypatch, served) -> None:
    server = served
    add(server, "first")
    monkeypatch.setattr(Device, "start", lambda self: None)
    shown, calls = phone(monkeypatch, Items, "Anyone", "first")
    port = free_port()
    surface = app(Environment("local", {"api": server.url}), port)
    surface.browser = shown
    surface.start()
    try:
        get(port, "/todos")
        surface.stepping()
        shown.fill(Items.who, "first")
        assert shown.list_faults() == []
    finally:
        surface.stop()


def test_a_list_whose_request_the_app_never_sent_is_a_fault(monkeypatch, served) -> None:
    server = served
    add(server, "first")
    monkeypatch.setattr(Device, "start", lambda self: None)
    shown, calls = phone(monkeypatch, Items, "Anyone", "first")
    shown.timeout = 0.0
    port = free_port()
    surface = app(Environment("local", {"api": server.url}), port)
    surface.browser = shown
    surface.start()
    try:
        surface.stepping()
        shown.fill(Items.who, "first")
        assert shown.list_faults() == ["the list Items.who is GET /todos, and the app sent no such request"]
    finally:
        surface.stop()


def test_a_surface_stopped_frees_its_port(monkeypatch, served) -> None:
    server = served
    monkeypatch.setattr(Device, "start", lambda self: None)
    shown, _ = phone(monkeypatch, Items, "Anyone")
    port = free_port()
    surface = app(Environment("local", {"api": server.url}), port)
    surface.browser = shown
    surface.start()
    surface.stop()

    Proxy(port, ("127.0.0.1", 1)).start().stop()
