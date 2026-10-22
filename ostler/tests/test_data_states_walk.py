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
from data_state_books import (API, ENDPOINTS, FIXTURE, FIXTURE_PAGE, FLOW, FLOW_PAGE, ISSUED, ISSUED_ARRANGED, PAID, PAY_MOVES,
                              RUNBOOK, RUNBOOK_PAGE, VOID, VOID_FROM_ISSUED, api_page, void_page)

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"
BASE_URL = "http://localhost:18101"
SCENARIO = "docs-services-acme-flows-pay-a-bill-journey"
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

LOGINS = """## Endpoints

### login-a
- method: POST
- path: /login-a
- arrange: no_body()
- status: 200 with the token
- capture: user_a from $.token
- verify: http_status(code=200)

### login-b
- method: POST
- path: /login-b
- arrange: no_body()
- status: 200 with the token
- capture: user_b from $.token
- verify: http_status(code=200)

### create-bill
- method: POST
- path: /bills
- arrange: no_body()
- status: 201 with the new bill
- capture: bill_id from $.id
- verify: http_status(code=201)
"""

SENT_AS_B = '- arrange: header(name="Authorization", value="Bearer $user_b")\n'
OBSERVED_AS_A = '- arrange: header(name="Authorization", value="Bearer $user_a")\n'


def _credentialed(root: Path, *, own: bool, observe_extra: str = "") -> str:
    pay = ("### pay-bill\n- method: POST\n" + ("- path: /me/pay\n" if own else "- path: /bills/{bill_id}/pay\n")
           + "- arrange: no_body()\n" + SENT_AS_B + PAY_MOVES + "- verify: http_status(code=200)\n")
    read = ("### read-bill\n- method: GET\n" + ("- path: /me/bill\n" if own else "- path: /bills/{bill_id}\n")
            + OBSERVED_AS_A + observe_extra + "- verify: http_status(code=200)\n")
    states = ISSUED.replace("#get-bill", "#read-bill") + "\n" + PAID.replace("#get-bill", "#read-bill")
    write(root / API, f"---\ntype: server\ntitle: Bills API\n---\n# Bills API\n\n- entry-url: http://localhost:18101\n\n"
                      f"{LOGINS}\n{pay}\n{read}\n## Data states\n\n{states}")
    steps = "".join(f"  - [{name}](../http/api.md#{name})\n" for name in ("login-a", "login-b", "create-bill", "pay-bill"))
    write(root / FLOW, FLOW_WITH_CHECK.replace("  - [create-bill](../http/api.md#create-bill)\n  - [pay-bill](../http/api.md#pay-bill)\n", steps))
    write(root / RUNBOOK, RUNBOOK_PAGE)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    planned = compile_plan_gaps(build_context(root, base="HEAD", whole_book=True), story="demo")
    assert isinstance(planned, Plan), [(g.obligation_id, g.detail[:60]) for g in planned.gaps if g.kind in ('unresolved-precondition',)]
    return planned.source


def _read_back_request(source: str) -> str:
    [line] = [line for line in source.splitlines() if "moved_" in line and "qa.http" in line]
    return line


def test_a_move_on_the_callers_own_record_reads_back_with_the_credential_the_step_sent(tmp_path: Path) -> None:
    line = _read_back_request(_credentialed(tmp_path, own=True))
    assert "user_b" in line
    assert "user_a" not in line


def test_a_move_on_a_record_a_path_variable_addresses_reads_back_with_the_observe_endpoints_own_headers(
    tmp_path: Path,
) -> None:
    line = _read_back_request(_credentialed(tmp_path, own=False))
    assert "user_a" in line
    assert "user_b" not in line


def test_the_callers_own_read_back_keeps_a_header_only_the_observe_endpoint_arranges(tmp_path: Path) -> None:
    extra = '- arrange: header(name="X-Trace", value="on")\n'
    line = _read_back_request(_credentialed(tmp_path, own=True, observe_extra=extra))
    assert "user_b" in line
    assert "user_a" not in line
    assert '"X-Trace": "on"' in line

OWN_READ = '- path: /me/bill\n- arrange: header(name="authorization", value="Bearer @someone-else.bill_id")\n- verify'
OWN_VOID = '- arrange: header(name="Authorization", value="Bearer @issued-bill.bill_id")\n'
SIGNED_IN = "docs/services/acme/fixtures/signed-in.md"
SIGNED_IN_PAGE = FIXTURE_PAGE.replace("bill_id", "token").replace("Issued bill", "Signed in").replace("an issued bill", "a token")


def _compiled(root: Path, page: str, *fixtures: tuple[str, str]):
    write(root / API, page)
    write(root / FLOW, FLOW_WITH_CHECK)
    write(root / RUNBOOK, RUNBOOK_PAGE)
    write(root / FIXTURE, FIXTURE_PAGE)
    for path, text in fixtures:
        write(root / path, text)
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return compile_plan_gaps(build_context(root, base="HEAD", whole_book=True), story="demo")


def test_the_starting_read_of_a_callers_own_move_sends_the_headers_the_step_sends(tmp_path: Path) -> None:
    void = (ENDPOINTS.replace("- path: /bills/{bill_id}\n- verify", OWN_READ)
            + "\n### void-bill\n- method: POST\n- path: /me/void\n- arrange: no_body()\n" + OWN_VOID + VOID_FROM_ISSUED
            + "- verify: http_status(code=200)\n")
    planned = _compiled(tmp_path, api_page(endpoints=void, states=ISSUED_ARRANGED + "\n" + VOID))
    assert isinstance(planned, Plan), [(g.obligation_id, g.detail[:80]) for g in planned.gaps]
    [before] = [line for line in planned.source.splitlines() if "before_move = qa.http" in line]
    assert "@issued-bill.bill_id" in before
    assert "someone-else" not in before


def _own_state_page(fixture: str) -> str:
    states = ISSUED + f"- fixture: [{fixture}](../fixtures/{fixture}.md)\n"
    return void_page(void_moves="- moves: none, because nothing changes\n", states=states).replace(
        "- path: /bills/{bill_id}\n- verify",
        "- path: /me/bill\n- arrange: header(name=\"Authorization\", value=\"Bearer @someone-else.token\")\n- verify")


def test_a_callers_own_state_read_sends_the_token_of_the_fixture_the_state_arranges(tmp_path: Path) -> None:
    planned = _compiled(tmp_path, _own_state_page("signed-in"), (SIGNED_IN, SIGNED_IN_PAGE))
    assert isinstance(planned, Plan), [(g.obligation_id, g.detail[:80]) for g in planned.gaps]
    [read] = [line for line in planned.source.splitlines() if "observed = qa.http.get" in line]
    assert "@signed-in.token" in read
    assert "someone-else" not in read


def test_a_callers_own_state_read_keeps_the_gap_when_the_fixture_provides_no_such_fact(tmp_path: Path) -> None:
    planned = _compiled(tmp_path, _own_state_page("issued-bill"))
    assert [gap for gap in planned.gaps if "@someone-else.token" in gap.detail]


ROLELESS = "docs/services/acme/fixtures/roleless.md"
ROLELESS_PAGE = SIGNED_IN_PAGE.replace("Signed in", "Roleless").replace("a token", "a roleless token")
AS_SIGNED_IN = '- arrange: header(name="Authorization", value="Bearer @signed-in.token")\n'


def _own_endpoints(*, move_path: str) -> str:
    return (ENDPOINTS.replace("- path: /bills/{bill_id}\n- verify", f"- path: /me/bill\n{AS_SIGNED_IN}- verify")
            + "\n### void-bill\n- method: POST\n" + f"- path: {move_path}\n- arrange: no_body()\n" + AS_SIGNED_IN
            + VOID_FROM_ISSUED + "- verify: http_status(code=200)\n")


CARRIES_SIGNED_IN = PAID + "- fixture: [signed-in](../fixtures/signed-in.md)\n"


def _roleless_move(root: Path, *, move_path: str):
    states = ISSUED + "- fixture: [roleless](../fixtures/roleless.md)\n\n" + CARRIES_SIGNED_IN + "\n" + VOID
    page = api_page(endpoints=_own_endpoints(move_path=move_path), states=states)
    return _compiled(root, page, (SIGNED_IN, SIGNED_IN_PAGE), (ROLELESS, ROLELESS_PAGE))


def test_a_callers_own_state_read_sends_the_token_of_the_state_fixture_the_endpoint_also_names(tmp_path: Path) -> None:
    states = ISSUED + "- fixture: [roleless](../fixtures/roleless.md)\n\n" + CARRIES_SIGNED_IN
    page = void_page(void_moves="- moves: none, because nothing changes\n", states=states).replace(
        "- path: /bills/{bill_id}\n- verify", f"- path: /me/bill\n{AS_SIGNED_IN}- verify")
    page = page.replace("- arrange: no_body()\n- verify: http_status(code=200)\n\n### void-bill",
                        f"- arrange: no_body()\n{AS_SIGNED_IN}- verify: http_status(code=200)\n\n### void-bill")
    planned = _compiled(tmp_path, page, (SIGNED_IN, SIGNED_IN_PAGE), (ROLELESS, ROLELESS_PAGE))
    assert isinstance(planned, Plan), [(g.obligation_id, g.detail[:80]) for g in planned.gaps]
    reads = [line for line in planned.source.splitlines() if "observed = qa.http.get" in line]
    assert sorted("@roleless.token" in line for line in reads) == [False, True]
    [roleless] = [line for line in reads if "@roleless.token" in line]
    assert "@signed-in.token" not in roleless


def test_a_callers_own_move_sends_the_token_of_the_starting_state_fixture(tmp_path: Path) -> None:
    planned = _roleless_move(tmp_path, move_path="/me/void")
    assert isinstance(planned, Plan), [(g.obligation_id, g.detail[:80]) for g in planned.gaps]
    requests = [line for line in planned.source.splitlines()
                if "before_move = qa.http" in line or "observed_1 = qa.http.post(\"/me/void\"" in line
                or "moved_" in line and "qa.http" in line]
    assert len(requests) == 3
    assert all("@roleless.token" in line and "@signed-in.token" not in line for line in requests)
    assert not [gap for gap in planned.gaps if gap.kind == "unresolved-precondition"]


def test_a_move_on_a_path_variable_record_keeps_the_endpoints_own_token(tmp_path: Path) -> None:
    planned = _roleless_move(tmp_path, move_path="/bills/{bill_id}/void")
    assert isinstance(planned, Plan)
    posts = [line for line in planned.source.splitlines() if "qa.http.post" in line and "void" in line]
    assert posts
    assert all("@signed-in.token" in line and "@roleless.token" not in line for line in posts)
