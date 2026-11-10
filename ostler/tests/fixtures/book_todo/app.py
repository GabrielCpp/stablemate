"""An in-memory todo service on the standard library, the stand-in a test starts for the todo book."""

from __future__ import annotations

import functools
import json
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

USERS = ("ana", "bo")
STATUSES = ("overdue", "scheduled", "unscheduled")
DATE_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def valid_date(text: str) -> bool:
    if not DATE_FORM.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def now() -> datetime:
    return datetime.now(timezone.utc)


class Todo:
    def __init__(self, ident: str, title: str, description: str | None, due_on: str | None,
                 assignee: str | None, created_at: str, seq: int) -> None:
        self.ident = ident
        self.title = title
        self.description = description
        self.due_on = due_on
        self.assignee = assignee
        self.created_at = created_at
        self.seq = seq


class Fields:
    def __init__(self, title: str, description: str | None, due_on: str | None, assignee: str | None) -> None:
        self.title = title
        self.description = description
        self.due_on = due_on
        self.assignee = assignee


class TodoStore:
    """The state of one service: the todos, the counter, the clock and the store switch."""

    def __init__(self, token: str, api_key: str, bug: str | None) -> None:
        self.token = token
        self.api_key = api_key
        self.bug = bug
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.todos: list[Todo] = []
        self.counter = 0
        self.down = False
        self.today = now().strftime("%Y-%m-%d")

    def view(self, todo: Todo) -> dict[str, Any]:
        if todo.due_on is None:
            status = "unscheduled"
        elif todo.due_on >= self.today:
            status = "scheduled"
        else:
            status = "overdue"
        return {
            "id": todo.ident, "title": todo.title, "description": todo.description, "due_on": todo.due_on,
            "assignee": todo.assignee, "status": status, "created_at": todo.created_at,
        }

    def find(self, ident: str) -> Todo | None:
        for todo in self.todos:
            if todo.ident == ident:
                return todo
        return None

    def parse_fields(self, body: dict[str, Any], current: Todo | None) -> tuple[Fields | None, str]:
        title = body.get("title")
        title = title.strip() if isinstance(title, str) else ""
        if not title:
            return None, "Title is required"
        if len(title) > 120:
            return None, "Title is too long"
        description: str | None = None
        if body.get("description") is not None:
            raw = body["description"]
            description = raw if isinstance(raw, str) else ""
            if len(description) > 2000:
                return None, "Description is too long"
        due_on: str | None = None
        if body.get("due_on") is not None:
            raw = body["due_on"]
            if not isinstance(raw, str) or not valid_date(raw):
                return None, "Due date must be a date"
            kept = current is not None and current.due_on == raw
            if raw < self.today and not kept:
                return None, "Due date cannot be in the past"
            due_on = raw
        assignee: str | None = None
        if body.get("assignee") is not None:
            raw = body["assignee"]
            if not isinstance(raw, str) or raw not in USERS:
                return None, "No such user"
            assignee = raw
        return Fields(title, description, due_on, assignee), ""

    def create_todo(self, body: dict[str, Any]) -> tuple[int, Any]:
        fields, message = self.parse_fields(body, None)
        if fields is None:
            return 400, {"error": message}
        self.counter += 1
        todo = Todo(str(uuid.uuid4()), fields.title, fields.description, fields.due_on, fields.assignee,
                    now().strftime("%Y-%m-%dT%H:%M:%SZ"), self.counter)
        self.todos.append(todo)
        return 201, self.view(todo)

    def put_todo(self, ident: str, body: dict[str, Any]) -> tuple[int, Any]:
        todo = self.find(ident)
        if todo is None:
            return 404, {"error": "Not found"}
        fields, message = self.parse_fields(body, todo)
        if fields is None:
            return 400, {"error": message}
        if self.bug != "update":
            todo.title, todo.description, todo.due_on, todo.assignee = fields.title, fields.description, fields.due_on, fields.assignee
        return 200, self.view(todo)

    def remove_todo(self, ident: str) -> tuple[int, Any]:
        todo = self.find(ident)
        if todo is None:
            return 404, {"error": "Not found"}
        self.todos.remove(todo)
        return 204, None

    def list_todos(self, query: dict[str, list[str]]) -> tuple[int, Any]:
        def first(name: str) -> str:
            return query.get(name, [""])[0]

        status, assignee, text = first("status"), first("assignee"), first("text").lower()
        if status and status not in STATUSES:
            return 400, {"error": "Unknown status"}
        found: list[tuple[Todo, dict[str, Any]]] = []
        for todo in self.todos:
            shown = self.view(todo)
            if status and shown["status"] != status:
                continue
            if assignee and shown["assignee"] != assignee:
                continue
            if text:
                haystack = shown["title"].lower()
                if shown["description"] is not None:
                    haystack += "\n" + shown["description"].lower()
                if text not in haystack:
                    continue
            found.append((todo, shown))
        found.sort(key=functools.cmp_to_key(self.order))
        return 200, [shown for _, shown in found]

    @staticmethod
    def order(left: tuple[Todo, dict[str, Any]], right: tuple[Todo, dict[str, Any]]) -> int:
        a, b = left[1], right[1]
        ra, rb = STATUSES.index(a["status"]), STATUSES.index(b["status"])
        if ra != rb:
            return -1 if ra < rb else 1
        if ra == 2:
            if a["created_at"] != b["created_at"]:
                return -1 if a["created_at"] > b["created_at"] else 1
            return -1 if left[0].seq > right[0].seq else 1
        if a["due_on"] != b["due_on"]:
            return -1 if a["due_on"] < b["due_on"] else 1
        return -1 if left[0].seq < right[0].seq else 1

    def todos_handler(self, method: str, path: str, query: dict[str, list[str]], headers: Any, body: bytes) -> tuple[int, Any]:
        if headers.get("Authorization") != f"Bearer {self.token}" and headers.get("X-Api-Key") != self.api_key:
            return 401, {"error": "Unauthorized"}
        with self.lock:
            if self.down:
                return 503, {"error": "Service unavailable"}
            ident = path.removeprefix("/todos").removeprefix("/")
            if not ident:
                if method == "POST":
                    parsed = read_body(body)
                    return (400, {"error": "Invalid JSON"}) if parsed is None else self.create_todo(parsed)
                if method == "GET":
                    return self.list_todos(query)
                return 405, {"error": "Method not allowed"}
            if method == "GET":
                todo = self.find(ident)
                return (404, {"error": "Not found"}) if todo is None else (200, self.view(todo))
            if method == "DELETE":
                return self.remove_todo(ident)
            if method == "PUT":
                parsed = read_body(body)
                return (400, {"error": "Invalid JSON"}) if parsed is None else self.put_todo(ident, parsed)
            return 405, {"error": "Method not allowed"}

    def admin_handler(self, method: str, path: str, body: bytes) -> tuple[int, Any]:
        if path == "/admin/clock" and method == "GET":
            with self.lock:
                return 200, {"today": self.today}
        if path == "/admin/clock" and method == "POST":
            decoded = read_object(body)
            today = decoded.get("today", "") if decoded is not None else None
            if decoded is None or not isinstance(today, str) or not valid_date(today):
                return 400, {"error": "Due date must be a date"}
            with self.lock:
                self.today = today
            return 204, None
        if path == "/admin/store" and method == "POST":
            decoded = read_object(body)
            down = decoded.get("down") if decoded is not None else None
            if decoded is None or (down is not None and not isinstance(down, bool)):
                return 400, {"error": "Invalid JSON"}
            with self.lock:
                self.down = bool(down)
            return 204, None
        if path == "/admin/reset" and method == "POST":
            with self.lock:
                self.reset()
            return 204, None
        return 404, {"error": "Not found"}


def read_value(body: bytes) -> tuple[bool, Any]:
    try:
        value, _ = json.JSONDecoder().raw_decode(body.decode().lstrip())
    except ValueError:
        return False, None
    return True, value


def read_body(body: bytes) -> dict[str, Any] | None:
    ok, value = read_value(body)
    return value if ok and isinstance(value, dict) else None


def read_object(body: bytes) -> dict[str, Any] | None:
    ok, value = read_value(body)
    if not ok:
        return None
    if value is None:
        return {}
    return value if isinstance(value, dict) else None


class TodoServer:
    """The service on a loopback port: `start` serves it on a thread, `stop` ends it."""

    def __init__(self, token: str = "test-token", api_key: str = "test-key", bug: str | None = None, port: int = 0) -> None:
        self.store = TodoStore(token, api_key, bug)
        store = self.store

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def __getattr__(self, name: str) -> Any:
                if name.startswith("do_"):
                    return self.serve
                raise AttributeError(name)

            def reply(self, status: int, body: Any = None, plain: str | None = None) -> None:
                payload = b"" if body is None and plain is None else (plain or json.dumps(body)).encode()
                self.send_response(status)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE")
                self.send_header("Access-Control-Allow-Headers", "Authorization, X-Api-Key, Content-Type")
                if payload:
                    self.send_header("Content-Type", "text/plain; charset=utf-8" if plain else "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload:
                    self.wfile.write(payload)

            def serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                if self.command == "OPTIONS":
                    self.reply(204)
                    return
                parts = urlsplit(self.path)
                if parts.path in ("/todos",) or parts.path.startswith("/todos/"):
                    status, payload = store.todos_handler(
                        self.command, parts.path, parse_qs(parts.query, keep_blank_values=True), self.headers, body)
                elif parts.path.startswith("/admin/"):
                    status, payload = store.admin_handler(self.command, parts.path, body)
                else:
                    self.reply(404, plain="404 page not found\n")
                    return
                self.reply(status, payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> TodoServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def serve_forever(self) -> None:
        self._server.serve_forever()


def main() -> None:
    server = TodoServer(os.environ.get("TOKEN", "test-token"), os.environ.get("API_KEY", "test-key"),
                        port=int(os.environ.get("PORT", "8080")))
    print("serving on", server.url, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
