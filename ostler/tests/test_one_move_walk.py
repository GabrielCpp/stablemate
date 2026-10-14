"""A move no flow takes gets a walk of its own: arrange the starting state, read the record there, send the move, hold the state it lands on."""

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
from data_state_books import (API, FIXTURE, FIXTURE_PAGE, FLOW, FLOW_PAGE, ISSUED, PAID_ARRANGED, PAID_FIXTURE,
                              PAID_FIXTURE_PAGE, PAY_MOVES, RUNBOOK, RUNBOOK_PAGE, VOID, VOID_FROM_ISSUED,
                              ISSUED_ARRANGED, void_page)

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"
BASE_URL = "http://localhost:18101"
VOID_REF = f"{API}#void-bill"
VOID_MOVE = f"okf:{VOID_REF}:moves:1"
FLOW_WITH_CHECK = FLOW_PAGE + '- fixture: none, because nothing is arranged\n- verify: http_status(code=200)\n'


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _plan(root: Path, page: str) -> Plan:
    write(root / API, page)
    write(root / FLOW, FLOW_WITH_CHECK)
    write(root / RUNBOOK, RUNBOOK_PAGE)
    write(root / FIXTURE, FIXTURE_PAGE)
    write(root / PAID_FIXTURE, PAID_FIXTURE_PAGE)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    planned = compile_plan_gaps(build_context(root, base="HEAD", whole_book=True), story="demo")
    assert isinstance(planned, Plan)
    return planned


def _stub(voids_to: str, starts: str = "issued") -> type[BaseHTTPRequestHandler]:
    bills = {"status": starts}

    class Bills(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.endswith("/void"):
                bills["status"] = voids_to
            elif self.path.endswith("/pay"):
                bills["status"] = "paid"
            self._send(200, {"id": "b-1", **bills})

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


def _scenario(planned: Plan) -> str:
    [name] = [line.split("(")[0].removeprefix("def ") for line in planned.source.splitlines()
              if line.startswith("def ") and "_void_bill_moves_1" in line]
    return name


def _walk(root: Path, planned: Plan, url: str, name: str | None = None) -> tuple[int, list[dict]]:
    module = root / "qa_plan.py"
    module.write_text(planned.source.replace(BASE_URL, url), encoding="utf-8")
    sink_path = root / "records.jsonl"
    seed = root / "seed.sh"
    seed.write_text('#!/bin/sh\necho \'{"bill": {"id": "b-1"}}\'\n', encoding="utf-8")
    seed.chmod(0o755)
    step = {"kind": "seed", "id": "seed-it", "command": str(seed), "cwd": str(root), "timeout": 5.0}
    fixtures = {name: {"steps": [step], "args": [], "needs": [], "secrets": [], "page": f"docs/fixtures/{name}.md",
                       "provides": [{"key": "bill_id", "from": "seed-it", "read": "bill.id"}]}
                for name in ("issued-bill", "paid-bill")}
    context = json.dumps({"root": str(root), "spec_dir": str(root), "qa_dir": str(root / "qa"),
                          "book_fixtures": fixtures, "lap_dir": ""})
    command = [sys.executable, "-m", "ostler_qa", "run", str(module), (name or _scenario(planned)).replace("_", "-"), context]
    with sink_path.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, pass_fds=(sink.fileno(),),
            env={"PYTHONPATH": str(HARNESS_DIR), "PATH": "/usr/bin:/bin", "OSTLER_QA_RECORD_FD": str(sink.fileno())},
        )
    records = [json.loads(line) for line in sink_path.read_text(encoding="utf-8").splitlines() if line]
    return done.returncode, records


def _held(records: list[dict]) -> list[dict]:
    return [r for r in records if r["type"] == "assert" and r["label"].startswith("the record")]


def _book(void_moves: str = VOID_FROM_ISSUED, states: str | None = None) -> str:
    if states is None:
        return void_page(void_moves=void_moves, pay_moves=PAY_MOVES)
    return void_page(void_moves=void_moves, pay_moves=PAY_MOVES, states=states)


def test_a_move_no_flow_takes_gets_a_walk_that_arranges_reads_sends_and_reads_back(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book())
    source = planned.source
    scenario = source[source.index(f"def {_scenario(planned)}"):]
    assert 'qa.fixture("issued-bill")' in scenario
    assert scenario.index("before_move") < scenario.index("/void") < scenario.index("moved_1")
    assert 'qa.holds("bill-issued"' in scenario
    assert 'qa.holds("bill-void"' in scenario
    assert VOID_MOVE in source
    assert not [gap for gap in planned.gaps if gap.obligation_id == VOID_MOVE]


def test_the_walk_passes_when_the_server_voids_the_bill(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book())
    with _serving(_stub("void")) as url:
        code, records = _walk(tmp_path, planned, url)
    assert code == 0, records
    assert [r["passed"] for r in _held(records)] == [True, True]


def test_the_walk_fails_at_the_void_step_when_the_server_leaves_the_bill_issued(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book())
    with _serving(_stub("issued")) as url:
        code, records = _walk(tmp_path, planned, url)
    assert code != 0
    failed = [r for r in _held(records) if not r["passed"]]
    [held] = failed
    assert held["node"] == VOID_REF
    assert "bill-issued" in held["label"]
    assert held["holds"] == "bill-issued"


def test_a_move_a_flow_takes_gets_no_walk_of_its_own(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book(void_moves="- moves: none, because nothing changes\n"))
    assert "_moves_" not in planned.source.replace("pay_bill_moves", "")
    pay_move = f"okf:{API}#pay-bill:moves:1"
    assert f'"{pay_move}"' in planned.source
    assert "_pay_bill_moves_1" not in planned.source


def test_a_move_whose_starting_state_has_no_fixture_is_uncovered_and_names_the_state(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book(states=ISSUED + "\n" + PAID_ARRANGED + "\n" + VOID))
    [gap] = [gap for gap in planned.gaps if gap.obligation_id == VOID_MOVE]
    assert gap.kind == "unarranged-state"
    assert "bill-issued" in gap.detail
    assert "_void_bill_moves_1" not in planned.source


def test_a_data_state_no_walk_reads_is_a_gap(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _book(states=ISSUED_ARRANGED + "\n" + PAID_ARRANGED + "\n" + VOID))
    state = f"okf:{API}#bill-void:contract"
    assert state in planned.source
    unread = _book(void_moves="- moves: none, because nothing changes\n")
    planned = _plan(tmp_path / "unread", unread)
    [gap] = [gap for gap in planned.gaps if gap.obligation_id == state]
    assert gap.kind == "unreached-data-state"
    assert "bill-void" in gap.detail


ISSUED_STATE = f"okf:{API}#bill-issued:contract"


def _lone_issued(fixture: bool = True) -> str:
    return void_page(void_moves="- moves: none, because nothing changes\n",
                     states=ISSUED_ARRANGED if fixture else ISSUED)


def _read_scenario(planned: Plan) -> str:
    source = planned.source
    return source[source.index(f"def {_read_name(planned)}"):]


def _read_name(planned: Plan) -> str:
    [name] = [line.split("(")[0].removeprefix("def ") for line in planned.source.splitlines()
              if line.startswith("def ") and "bill_issued_reads" in line]
    return name


def test_a_data_state_with_a_fixture_and_no_move_gets_a_walk_that_arranges_and_reads_it(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _lone_issued())
    assert not [gap for gap in planned.gaps if gap.obligation_id == ISSUED_STATE]
    scenario = _read_scenario(planned)
    assert 'qa.fixture("issued-bill")' in scenario
    assert scenario.index("qa.fixture") < scenario.index("observed = qa.http.get")
    assert 'qa.holds("bill-issued"' in scenario
    assert ISSUED_STATE in planned.source


def test_the_observe_walk_passes_when_the_server_answers_the_state_checks(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _lone_issued())
    with _serving(_stub("void")) as url:
        code, records = _walk(tmp_path, planned, url, _read_name(planned))
    assert code == 0, records
    assert [r["passed"] for r in _held(records)] == [True]


def test_the_observe_walk_fails_when_the_server_answers_otherwise(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _lone_issued())
    with _serving(_stub("void", starts="paid")) as url:
        code, records = _walk(tmp_path, planned, url, _read_name(planned))
    assert code != 0
    assert [r["passed"] for r in _held(records)] == [False]


def test_a_data_state_with_no_fixture_and_no_move_stays_unreached(tmp_path: Path) -> None:
    planned = _plan(tmp_path, _lone_issued(fixture=False))
    [gap] = [gap for gap in planned.gaps if gap.obligation_id == ISSUED_STATE]
    assert gap.kind == "unreached-data-state"
    assert "Add `- fixture:`" in gap.detail
    assert "bill_issued_reads" not in planned.source
