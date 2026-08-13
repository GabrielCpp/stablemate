"""A default-deny broker for the few host commands a sandboxed scenario may still need.

The sandbox removes a capability rather than forbidding it: with no repository on disk, a
scenario cannot rerun a unit suite and file the exit code as behavioral evidence. But some
legitimate evidence genuinely needs the host — a device the container has no path to, a
tool that is licensed to the machine. Reopening that door with a general "run this on the
host" escape hatch would hand the whole capability back and leave the guarantee where it
started, as a request in a prompt.

So the door is a **verb** list, not a shell. The repository declares the exact argv of each
thing a scenario may ask for; a scenario names a verb and supplies arguments; anything not
declared is refused with a reason. The list is empty unless someone deliberately widened
it, which means the default posture of a sandboxed run is that nothing reaches the host.

Every request is written to the ledger — allowed and denied alike. A denial that leaves no
trace is a capability that appears not to have been attempted, and the whole point of this
exercise is that what QA tried is legible afterwards.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ostler.qa.session import QaSession

#: How long a brokered command may run before it is killed. A verb is meant to be a probe,
#: not a build; a scenario that needs longer is describing a background service, which is
#: what `background:` in the plan is for.
VERB_TIMEOUT = 120.0

#: Cap on a brokered command's captured output, so a chatty tool cannot push the scenario's
#: own account out of the ledger.
OUTPUT_LIMIT = 64 * 1024


@dataclass(frozen=True)
class Verb:
    """One thing a sandboxed scenario is allowed to ask the host to do."""

    name: str
    argv: tuple[str, ...]
    timeout: float = VERB_TIMEOUT

    @classmethod
    def parse(cls, raw: Any) -> "Verb":
        if not isinstance(raw, dict) or not raw.get("verb") or not raw.get("argv"):
            raise ValueError(f"a gateway allow entry needs `verb` and `argv`: {raw!r}")
        argv = [str(part) for part in raw["argv"]]
        if not argv:
            raise ValueError(f"gateway verb {raw['verb']!r} declares an empty argv")
        return cls(
            name=str(raw["verb"]),
            argv=tuple(argv),
            timeout=float(raw.get("timeout", VERB_TIMEOUT)),
        )


class Gateway:
    """The host-side broker, bound for the length of one run.

    Bound on every interface, not loopback: the caller is a container, which reaches the
    host through the docker bridge and never through the host's own `127.0.0.1`. What keeps
    that from being an open door is the bearer token — freshly minted per run, carried to
    the scenario in its environment, and required on every route including health.
    """

    def __init__(self, session: QaSession, root: Path, allow: list[Verb]) -> None:
        self.session = session
        self.root = root
        self.verbs = {verb.name: verb for verb in allow}
        self.token = secrets.token_urlsafe(32)
        self.port = 0
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        # The ledger is a file appended from the run's main thread; the handler threads
        # write to it too, so audit records take a lock rather than racing a scenario_stop.
        self._ledger_lock = threading.Lock()

    def start(self) -> None:
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())  # noqa: S104
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.audit("start", "opened", f"{len(self.verbs)} verb(s) allowed")

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def audit(self, verb: str, decision: str, reason: str, **extra: Any) -> None:
        with self._ledger_lock:
            self.session.append(
                {"kind": "gateway", "verb": verb, "decision": decision, "reason": reason, **extra}
            )

    # -- the two routes -------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return {"ok": True, "verbs": sorted(self.verbs)}

    def execute(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        name = str(payload.get("verb", ""))
        verb = self.verbs.get(name)
        if verb is None:
            reason = (
                f"'{name}' is not an allowed verb"
                if name
                else "no verb named"
            ) + (
                f" — this run allows {sorted(self.verbs)}"
                if self.verbs
                else " — this run allows nothing on the host, which is the default"
            )
            self.audit(name, "denied", reason)
            return 403, {"error": reason}

        raw_args = payload.get("args", [])
        if not isinstance(raw_args, list) or any(not isinstance(arg, str) for arg in raw_args):
            reason = "`args` must be a list of strings"
            self.audit(name, "denied", reason)
            return 400, {"error": reason}

        argv = [*verb.argv, *raw_args]
        try:
            done = subprocess.run(  # noqa: S603 — argv[0] comes from the repo's own allow list
                argv,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=verb.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            reason = f"'{name}' exceeded its {verb.timeout:g}s budget and was killed"
            self.audit(name, "allowed", reason, exit_code=None)
            return 504, {"error": reason}
        except OSError as exc:
            reason = f"'{name}' could not be started: {exc}"
            self.audit(name, "allowed", reason, exit_code=None)
            return 500, {"error": reason}

        self.audit(name, "allowed", " ".join(argv), exit_code=done.returncode)
        return 200, {
            "exitCode": done.returncode,
            "stdout": (done.stdout or "")[:OUTPUT_LIMIT],
            "stderr": (done.stderr or "")[:OUTPUT_LIMIT],
        }

    # -- plumbing -------------------------------------------------------------------------

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                """The ledger is the log. stderr noise would interleave with a scenario's."""

            def _reply(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                scheme, _, presented = header.partition(" ")
                # Constant-time: the token is the only thing standing between this port and
                # every other container on the compose network.
                return scheme.lower() == "bearer" and secrets.compare_digest(
                    presented.strip(), gateway.token
                )

            def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                if not self._authorized():
                    gateway.audit("", "denied", f"unauthenticated GET {self.path}")
                    self._reply(401, {"error": "a bearer token is required"})
                    return
                if self.path.rstrip("/") == "/v1/health":
                    self._reply(200, gateway.health())
                    return
                self._reply(404, {"error": f"no such route: {self.path}"})

            def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                if not self._authorized():
                    gateway.audit("", "denied", f"unauthenticated POST {self.path}")
                    self._reply(401, {"error": "a bearer token is required"})
                    return
                if self.path.rstrip("/") != "/v1/exec":
                    self._reply(404, {"error": f"no such route: {self.path}"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError as exc:
                    self._reply(400, {"error": f"body is not JSON: {exc}"})
                    return
                if not isinstance(payload, dict):
                    self._reply(400, {"error": "body must be a JSON object"})
                    return
                status, body = gateway.execute(payload)
                self._reply(status, body)

        return Handler
