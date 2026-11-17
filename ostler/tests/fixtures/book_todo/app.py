"""An in-memory todo service on the standard library, the stand-in a test starts for the todo book."""

from __future__ import annotations

import base64
import functools
import json
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

USERS = ("ana", "bo")
ROSTER = ("bo", "ana")
TOKEN_LIFE = 3600
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


def moment(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def now() -> datetime:
    return datetime.now(timezone.utc)


class Todo:
    def __init__(self, ident: str, title: str, description: str | None, due_on: str | None,
                 assignee: str | None, created_at: str, seq: int, remind_at: str | None = None,
                 owner: str | None = None) -> None:
        self.owner = owner
        self.ident = ident
        self.title = title
        self.description = description
        self.due_on = due_on
        self.assignee = assignee
        self.created_at = created_at
        self.seq = seq
        self.remind_at = remind_at


class Fields:
    def __init__(self, title: str, description: str | None, due_on: str | None, assignee: str | None,
                 remind_at: str | None = None) -> None:
        self.remind_at = remind_at
        self.title = title
        self.description = description
        self.due_on = due_on
        self.assignee = assignee


class TodoStore:
    """The state of one service: the todos, the counter, the clock and the store switch."""

    def __init__(self, token: str, api_key: str, bug: str | None, sign_in: bool = False,
                 clock: Callable[[], float] = time.time) -> None:
        self.token = token
        self.api_key = api_key
        self.bug = bug
        self.sign_in = sign_in
        self.clock = clock
        self.start_day = now().strftime("%Y-%m-%d")
        self.issued: dict[str, float] = {}
        self.persons: dict[str, str] = {}
        self.sessions: dict[str, str] = {}
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.todos: list[Todo] = []
        self.counter = 0
        self.down = False
        self.today = self.start_day
        self.persons = {}
        self.sessions = {}

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
            "remind_at": todo.remind_at, "remind_day": self.remind_day(todo.remind_at),
        }

    def untitled(self) -> dict[str, Any]:
        return self.view(Todo("6f1d8a52-3c4e-4b7a-9d20-1a2b3c4d5e6f", "", None, None, None, "2026-01-01T00:00:00Z", 0))

    def remind_day(self, remind_at: str | None) -> str | None:
        if remind_at is None:
            return None
        if self.bug == "remind_utc":
            parsed = moment(remind_at)
            return parsed.astimezone(timezone.utc).date().isoformat() if parsed is not None else None
        return remind_at[:10]

    def find(self, ident: str, who: str | None = None) -> Todo | None:
        for todo in self.todos:
            if todo.ident == ident and todo.owner == who:
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
        remind_at: str | None = None
        if body.get("remind_at") is not None:
            raw = body["remind_at"]
            if not isinstance(raw, str) or moment(raw) is None:
                return None, "Reminder must be a date-time"
            remind_at = raw
        return Fields(title, description, due_on, assignee, remind_at), ""

    def create_todo(self, body: dict[str, Any], who: str | None = None) -> tuple[int, Any]:
        fields, message = self.parse_fields(body, None)
        if fields is None:
            return 400, {"error": message}
        self.counter += 1
        todo = Todo(str(uuid.uuid4()), fields.title, fields.description, fields.due_on, fields.assignee,
                    now().strftime("%Y-%m-%dT%H:%M:%SZ"), self.counter, fields.remind_at, who)
        self.todos.append(todo)
        return 201, self.view(todo)

    def put_todo(self, ident: str, body: dict[str, Any], who: str | None = None) -> tuple[int, Any]:
        todo = self.find(ident, who)
        if todo is None:
            return 404, {"error": "Not found"}
        fields, message = self.parse_fields(body, todo)
        if fields is None:
            return 400, {"error": message}
        if self.bug != "update":
            todo.title, todo.description, todo.due_on, todo.assignee = fields.title, fields.description, fields.due_on, fields.assignee
            todo.remind_at = fields.remind_at
        return 200, self.view(todo)

    def remove_todo(self, ident: str, who: str | None = None) -> tuple[int, Any]:
        todo = self.find(ident, who)
        if todo is None:
            return 404, {"error": "Not found"}
        self.todos.remove(todo)
        return 204, None

    def list_todos(self, query: dict[str, list[str]], who: str | None = None) -> tuple[int, Any]:
        def first(name: str) -> str:
            return query.get(name, [""])[0]

        status, assignee, text = first("status"), first("assignee"), first("text").lower()
        if status and status not in STATUSES:
            return 400, {"error": "Unknown status"}
        found: list[tuple[Todo, dict[str, Any]]] = []
        for todo in self.todos:
            if todo.owner != who:
                continue
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
        listed = [shown for _, shown in found]
        if self.bug == "blank" and not (status or assignee or text):
            listed.insert(0, self.untitled())
        if self.bug == "offshape" and not (status or assignee or text):
            listed.insert(0, {**self.untitled(), "status": "limbo"})
        if self.bug in ("ghost", "ghost_drift") and not (status or assignee or text) and listed:
            if self.bug == "ghost_drift":
                listed[-1] = {**listed[-1], "description": "drifted"}
            listed.append({**listed[0], "title": ""})
        if self.bug == "stranger":
            listed.append(self.untitled())
        if self.bug == "repeat" and listed:
            listed.append(listed[0])
        return 200, listed

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

    def identify(self, headers: Any) -> tuple[bool, str | None]:
        """Whether the call carries an accepted credential, and the person it belongs to, if any."""
        if headers.get("Authorization") == f"Bearer {self.token}" or headers.get("X-Api-Key") == self.api_key:
            return True, None
        bearer = headers.get("Authorization", "").removeprefix("Bearer ")
        with self.lock:
            if bearer in self.sessions:
                return True, self.sessions[bearer]
            return self.sign_in and self.issued.get(bearer, 0.0) > self.clock(), None

    def authorised(self, headers: Any) -> bool:
        return self.identify(headers)[0]

    def sign_in_handler(self, method: str, body: bytes = b"") -> tuple[int, Any]:
        asked = read_body(body)
        if method == "POST" and asked is not None and "handle" in asked:
            handle, password = asked.get("handle"), asked.get("password")
            with self.lock:
                if not isinstance(handle, str) or not isinstance(password, str) or self.persons.get(handle) != password:
                    return 401, {"error": "Unauthorized"}
                token = uuid.uuid4().hex
                self.sessions[token] = handle
            return 200, {"token": token}
        if not self.sign_in or method != "POST":
            return 404, {"error": "Not found"}
        with self.lock:
            expires = int(self.clock()) + TOKEN_LIFE
            claims = {"exp": expires, "jti": len(self.issued)}
            parts = [base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode()
                     for part in ({"alg": "none"}, claims)]
            token = ".".join([*parts, "signature"])
            self.issued[token] = float(expires)
        return 200, {"token": token}

    def todos_handler(self, method: str, path: str, query: dict[str, list[str]], headers: Any, body: bytes) -> tuple[int, Any]:
        authorised, who = self.identify(headers)
        if not authorised:
            return 401, {"error": "Unauthorized"}
        with self.lock:
            if self.down:
                return 503, {"error": "Service unavailable"}
            ident = path.removeprefix("/todos").removeprefix("/")
            if not ident:
                if method == "POST":
                    parsed = read_body(body)
                    return (400, {"error": "Invalid JSON"}) if parsed is None else self.create_todo(parsed, who)
                if method == "GET":
                    return self.list_todos(query, who)
                return 405, {"error": "Method not allowed"}
            if method == "GET":
                todo = self.find(ident, who)
                return (404, {"error": "Not found"}) if todo is None else (200, self.view(todo))
            if method == "DELETE":
                return self.remove_todo(ident, who)
            if method == "PUT":
                parsed = read_body(body)
                return (400, {"error": "Invalid JSON"}) if parsed is None else self.put_todo(ident, parsed, who)
            return 405, {"error": "Method not allowed"}

    def users_handler(self, method: str, headers: Any) -> tuple[int, Any]:
        if not self.authorised(headers):
            return 401, {"error": "Unauthorized"}
        if method != "GET":
            return 405, {"error": "Method not allowed"}
        return 200, [{"name": name} for name in ROSTER]

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
        if path == "/admin/persons" and method == "POST":
            decoded = read_object(body)
            handle = decoded.get("handle") if decoded is not None else None
            if not isinstance(handle, str) or not handle:
                return 400, {"error": "Invalid JSON"}
            with self.lock:
                if handle in self.persons:
                    return 400, {"error": "Person exists"}
                self.persons[handle] = uuid.uuid4().hex
                return 201, {"handle": handle, "password": self.persons[handle]}
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

    def __init__(self, token: str = "test-token", api_key: str = "test-key", bug: str | None = None, port: int = 0,
                 sign_in: bool = False, clock: Callable[[], float] = time.time) -> None:
        self.store = TodoStore(token, api_key, bug, sign_in, clock)
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
                elif parts.path == "/sign-in":
                    status, payload = store.sign_in_handler(self.command, body)
                elif parts.path == "/users":
                    status, payload = store.users_handler(self.command, self.headers)
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
