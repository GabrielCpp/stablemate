"""A compiled journey across two real HTTP services: create on one, read back through the other."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import write
from ostler.qa import cmd_run
from ostler.qa.run import QaOutcome
from ostler.qa.compile import annotate_deferred_obligations, compile_plan
from ostler.qa.context import build_context, write_context

BOOK = "docs/services/tool"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _Fleet:
    """The two services: alpha creates things, beta reads the record that corresponds to an id."""

    def __init__(self, port_a: int, port_b: int) -> None:
        self.records: dict[str, dict[str, str]] = {}
        self.seen_a: list[tuple[str, str]] = []
        self.seen_b: list[tuple[str, str]] = []
        self.next_id = 0
        self.lock = threading.Lock()
        self.server_a = self._serve(port_a, self._alpha())
        self.server_b = self._serve(port_b, self._beta())

    @staticmethod
    def _serve(port: int, handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _alpha(self) -> type[BaseHTTPRequestHandler]:
        fleet = self

        class Alpha(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

            def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                with fleet.lock:
                    fleet.next_id += 1
                    thing_id = f"t{fleet.next_id}"
                    fleet.records[thing_id] = {"id": thing_id, "name": body.get("name", "")}
                fleet.seen_a.append(("POST", self.path))
                payload = json.dumps({"thing": {"id": thing_id}}).encode()
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                fleet.seen_a.append(("GET", self.path))
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        return Alpha

    def _beta(self) -> type[BaseHTTPRequestHandler]:
        fleet = self

        class Beta(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

            def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
                fleet.seen_b.append(("GET", self.path))
                thing_id = self.path.rsplit("/", 1)[-1]
                record = fleet.records.get(thing_id)
                if record is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                payload = json.dumps({"thing": record}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Beta

    def close(self) -> None:
        self.server_a.shutdown()
        self.server_a.server_close()
        self.server_b.shutdown()
        self.server_b.server_close()


@pytest.fixture
def fleet() -> Iterator[_Fleet]:
    pair = _Fleet(_free_port(), _free_port())
    yield pair
    pair.close()


def _book(root: Path, port_a: int, port_b: int) -> None:
    (root / BOOK / "http").mkdir(parents=True)
    (root / BOOK / "flows").mkdir(parents=True)
    (root / BOOK / "ops").mkdir(parents=True)
    write(root / BOOK / "http/alpha.md", f"""---
type: server
slug: alpha
title: Alpha
---
# Alpha

- entry-url: http://127.0.0.1:{port_a}

## Endpoints

### create-thing

- method: `POST`
- path: `/things`
- does: creates a thing and answers with it.
  - arrange: body(field="name", value="Widget A")
  - capture: thing_id from $.thing.id
""")
    write(root / BOOK / "http/beta.md", f"""---
type: server
slug: beta
title: Beta
---
# Beta

- entry-url: http://127.0.0.1:{port_b}

## Endpoints

### read-thing

- method: `GET`
- path: `/things/{{thing_id}}`
- does: reads the thing the journey made.
""")
    write(root / BOOK / "ops/stack.md", f"""---
type: runbook
title: Stack
---
# Stack

- driver: http
- surfaces: [Alpha](../http/alpha.md), [Beta](../http/beta.md)
- entry-url: http://127.0.0.1:{port_a}
- stop: pkill serve

## Steps

### serve

- kind: service
- run: ./serve.sh
""")
    write(root / BOOK / "flows/cross-servers.md", """---
type: flow
slug: cross-servers
title: Cross servers
---
# Cross servers

- start: both servers answer
- steps:
  1. Creates a thing on [alpha](../http/alpha.md#create-thing).
  2. Reads it back from [beta](../http/beta.md#read-thing).
- end: the created thing is read back from the second server
- verify: http_status(200, path="/things/$thing_id")
- fixture: none, because the two servers hold the whole world
""")


def _compiled(root: Path, fleet: _Fleet, name: str = "s1") -> Path:
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    context = build_context(root, base=_git(root, "rev-parse", "HEAD"), whole_book=True, books=[BOOK])
    annotate_deferred_obligations(context, story=name)
    spec_dir = root / f"art/specs/{name}"
    write_context(context, spec_dir)
    plan = compile_plan(context, story=name)
    write(spec_dir / "qa_plan.py", plan)
    return spec_dir


def test_the_compiled_journey_creates_on_one_server_and_reads_back_through_the_other(
    tmp_path: Path, fleet: _Fleet,
) -> None:
    _book(tmp_path, fleet.server_a.server_address[1], fleet.server_b.server_address[1])
    spec_dir = _compiled(tmp_path, fleet)

    outcome = cmd_run(spec_dir / "qa_plan.py", spec_dir, root=tmp_path)

    assert outcome.ok, outcome.message
    assert fleet.seen_a == [("POST", "/things")]
    created_id = next(iter(fleet.records))
    assert fleet.seen_b == [("GET", f"/things/{created_id}")], \
        "the read reached the second server for the id the first server minted"


def test_a_journey_routed_to_the_wrong_server_fails(tmp_path: Path, fleet: _Fleet) -> None:
    _book(tmp_path, fleet.server_a.server_address[1], fleet.server_b.server_address[1])
    spec_dir = _compiled(tmp_path, fleet)
    plan_path = spec_dir / "qa_plan.py"
    other_var = f"tool_api_127_0_0_1_{fleet.server_b.server_address[1]}"
    plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
        f'qa.http_for("{other_var}")', "qa.http"), encoding="utf-8")

    outcome = cmd_run(plan_path, spec_dir, root=tmp_path)

    assert not outcome.ok
    assert fleet.seen_b == [], "the read never reached the server the book named for it"
    assert [method for method, _ in fleet.seen_a] == ["POST", "GET"]


def test_a_journey_that_loses_the_capture_fails(tmp_path: Path, fleet: _Fleet) -> None:
    _book(tmp_path, fleet.server_a.server_address[1], fleet.server_b.server_address[1])
    spec_dir = _compiled(tmp_path, fleet)
    plan_path = spec_dir / "qa_plan.py"
    plan_path.write_text(plan_path.read_text(encoding="utf-8").replace(
        '    qa.capture_field("thing_id", observed_1.json(), "thing.id")\n', ""), encoding="utf-8")

    outcome = cmd_run(plan_path, spec_dir, root=tmp_path)

    assert not outcome.ok
    assert fleet.seen_b == [], "with the capture lost, the second server was never read"


def test_a_dead_second_server_closes_the_ledger_and_leaks_nothing(tmp_path: Path, fleet: _Fleet) -> None:
    _book(tmp_path, fleet.server_a.server_address[1], fleet.server_b.server_address[1])
    spec_dir = _compiled(tmp_path, fleet)
    fleet.server_b.shutdown()
    fleet.server_b.server_close()

    outcome = cmd_run(spec_dir / "qa_plan.py", spec_dir, root=tmp_path)

    assert not outcome.ok
    ledger = (spec_dir / "qa/qa-run.ndjson").read_text(encoding="utf-8")
    assert '"kind": "session_stop"' in ledger, "the interrupted run still closed its ledger"
    assert fleet.seen_a == [("POST", "/things")]


def test_two_concurrent_journeys_keep_their_targets_and_captures_apart(
    tmp_path: Path, fleet: _Fleet,
) -> None:
    port_a, port_b = fleet.server_a.server_address[1], fleet.server_b.server_address[1]
    first = tmp_path / "first"
    second = tmp_path / "second"
    _book(first, port_a, port_b)
    _book(second, port_a, port_b)
    spec_first = _compiled(first, fleet, "s1")
    spec_second = _compiled(second, fleet, "s2")
    results: dict[str, QaOutcome] = {}

    def run(name: str, spec_dir: Path) -> None:
        results[name] = cmd_run(spec_dir / "qa_plan.py", spec_dir, root=spec_dir.parents[2])

    threads = [
        threading.Thread(target=run, args=("first", spec_first)),
        threading.Thread(target=run, args=("second", spec_second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results["first"].ok and results["second"].ok
    assert len(fleet.records) == 2, "each journey created its own record"
    reads = sorted(path for _method, path in fleet.seen_b)
    assert reads == sorted(f"/things/{thing_id}" for thing_id in fleet.records), \
        "each read asked the second server for the id its own journey captured"
