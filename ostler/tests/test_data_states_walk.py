"""A compiled http walk reads back the data state a step's `moves:` row names, against a live stub server."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ostler.qa.compile import Plan, compile_plan_gaps
from ostler.qa.context import build_context

from conftest import write
from data_state_books import API, FLOW, FLOW_PAGE, PAY_MOVES, RUNBOOK, RUNBOOK_PAGE, api_page

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"
BASE_URL = "http://localhost:18101"
SCENARIO = "docs-features-acme-flows-pay-a-bill-journey"
PAY_REF = f"{API}#pay-bill"
FLOW_WITH_CHECK = FLOW_PAGE + '- fixture: none, because nothing is arranged\n- verify: http_status(code=200)\n'


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _plan(root: Path, pay_moves: str) -> Plan:
    write(root / API, api_page(pay_moves=pay_moves))
    write(root / FLOW, FLOW_WITH_CHECK)
    write(root / RUNBOOK, RUNBOOK_PAGE)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    planned = compile_plan_gaps(build_context(root, base="HEAD", whole_book=True), story="demo")
    assert isinstance(planned, Plan)
    return planned


def _stub(pays_to: str) -> type[BaseHTTPRequestHandler]:
    bills = {"status": "issued"}

    class Bills(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.endswith("/pay"):
                bills["status"] = pays_to
                self._send(200, {"id": "b-1", **bills})
            else:
                self._send(201, {"id": "b-1", **bills})

        def do_GET(self) -> None:  # noqa: N802
            self._send(200, {"id": "b-1", **bills})

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Bills


@contextmanager
def _serving(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _walk(root: Path, source: str, url: str) -> tuple[int, list[dict]]:
    module = root / "qa_plan.py"
    module.write_text(source.replace(BASE_URL, url), encoding="utf-8")
    sink_path = root / "records.jsonl"
    context = json.dumps({"root": str(root), "spec_dir": str(root), "qa_dir": str(root / "qa")})
    command = [sys.executable, "-m", "ostler_qa", "run", str(module), SCENARIO, context]
    with sink_path.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, pass_fds=(sink.fileno(),),
            env={"PYTHONPATH": str(HARNESS_DIR), "PATH": "/usr/bin:/bin", "OSTLER_QA_RECORD_FD": str(sink.fileno())},
        )
    records = [json.loads(line) for line in sink_path.read_text(encoding="utf-8").splitlines() if line]
    return done.returncode, records


def _held(records: list[dict]) -> list[dict]:
    return [r for r in records if r["type"] == "assert" and r["label"].startswith("the record")]


def test_a_move_the_server_makes_passes_the_walk(tmp_path: Path) -> None:
    planned = _plan(tmp_path, PAY_MOVES)
    with _serving(_stub("paid")) as url:
        code, records = _walk(tmp_path, planned.source, url)
    assert code == 0, records
    [held] = _held(records)
    assert held["passed"] is True
    assert held["actual"] == "bill-paid"


def test_a_move_the_server_does_not_make_fails_at_the_step_and_names_the_state_that_holds(tmp_path: Path) -> None:
    planned = _plan(tmp_path, PAY_MOVES)
    with _serving(_stub("issued")) as url:
        code, records = _walk(tmp_path, planned.source, url)
    assert code != 0
    [held] = _held(records)
    assert held["passed"] is False
    assert held["node"] == PAY_REF
    assert "bill-issued" in held["label"]
    assert held["holds"] == "bill-issued"


def test_a_record_in_no_state_of_the_lifecycle_says_so(tmp_path: Path) -> None:
    planned = _plan(tmp_path, PAY_MOVES)
    with _serving(_stub("void")) as url:
        code, records = _walk(tmp_path, planned.source, url)
    assert code != 0
    [held] = _held(records)
    assert held["node"] == PAY_REF
    assert "no state of the lifecycle" in held["label"]


def test_a_move_that_only_lands_reads_back_the_same_way(tmp_path: Path) -> None:
    both = _plan(tmp_path / "both", PAY_MOVES)
    landing = _plan(tmp_path / "landing", "- moves: to [Bill paid](#bill-paid)\n")
    read_back = [line for line in both.source.splitlines() if "moved_" in line or "qa.holds" in line]
    assert read_back
    assert [line for line in landing.source.splitlines() if "moved_" in line or "qa.holds" in line] == read_back


def test_a_move_of_none_adds_no_read_back(tmp_path: Path) -> None:
    planned = _plan(tmp_path, "- moves: none, because the pay answer is the whole change\n")
    assert "qa.holds" not in planned.source
    assert "moved_" not in planned.source


def test_two_moves_rows_read_back_both_states(tmp_path: Path) -> None:
    planned = _plan(tmp_path, PAY_MOVES + "- moves: to [Bill issued](#bill-issued)\n")
    assert planned.source.count("qa.holds(") == 2
    assert 'qa.holds("bill-paid"' in planned.source
    assert 'qa.holds("bill-issued"' in planned.source


