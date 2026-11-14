"""A digest service on the standard library: it keeps nothing and answers from the todo API it calls."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

FORWARDED = ("Authorization", "X-Api-Key")


class Digest:
    """What the service does with the todo API's answers: it holds only the ones that are late."""

    def __init__(self, todo_url: str, bug: str | None) -> None:
        self.todo_url = todo_url.rstrip("/")
        self.bug = bug

    def ask(self, path: str, headers: Any, method: str = "GET") -> tuple[int, Any]:
        forwarded = {name: headers[name] for name in FORWARDED if headers.get(name) is not None}
        try:
            with urlopen(Request(self.todo_url + path, headers=forwarded, method=method), timeout=10) as reply:
                return reply.status, json.loads(reply.read() or "null")
        except HTTPError as reply:
            raw = reply.read()
            body = json.loads(raw) if raw else None
            if self.bug == "digest-hides-missing" and reply.code == 404:
                return 500, {"error": "Internal Server Error"}
            return reply.code, body

    def kept(self, todo: dict[str, Any]) -> bool:
        if self.bug == "digest-keeps-scheduled":
            return todo["status"] in ("overdue", "scheduled")
        return todo["status"] == "overdue"

    def digest(self, headers: Any) -> tuple[int, Any]:
        status, body = self.ask("/todos", headers)
        if status != 200:
            return status, body
        late = [{"id": todo["id"], "label": todo["title"]} for todo in body if self.kept(todo)]
        return 200, {"late": late, "count": len(late)}

    def entry(self, ident: str, headers: Any) -> tuple[int, Any]:
        status, body = self.ask("/todos/" + ident, headers)
        if status != 200:
            return status, body
        return 200, {"id": body["id"], "label": body["title"], "late": body["status"] == "overdue"}

    def done(self, ident: str, headers: Any) -> tuple[int, Any]:
        if self.bug == "digest-drops-done":
            return 204, None
        return self.ask("/todos/" + ident, headers, "DELETE")


class DigestServer:
    """The service on a loopback port: `start` serves it on a thread, `stop` ends it."""

    def __init__(self, todo_url: str, bug: str | None = None, port: int = 0) -> None:
        digest = Digest(todo_url, bug)

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/digest":
                    status, payload = digest.digest(self.headers)
                elif path.startswith("/digest/"):
                    status, payload = digest.entry(path.removeprefix("/digest/"), self.headers)
                else:
                    status, payload = 404, {"error": "Not found"}
                self.answer(status, payload)

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                path = self.path.split("?", 1)[0]
                if path.startswith("/digest/") and path.endswith("/done"):
                    status, payload = digest.done(path.removeprefix("/digest/").removesuffix("/done"), self.headers)
                else:
                    status, payload = 404, {"error": "Not found"}
                self.answer(status, payload)

            def answer(self, status: int, payload: Any) -> None:
                raw = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                if raw:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> DigestServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def serve_forever(self) -> None:
        self._server.serve_forever()


def main() -> None:
    server = DigestServer(os.environ.get("TODO_URL", "http://127.0.0.1:8080"), os.environ.get("BUG") or None,
                          port=int(os.environ.get("PORT", "8082")))
    print("serving on", server.url, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
