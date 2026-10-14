"""A flow step states no result, each outcome checks more than its status, each write names its moves, and a flow's own refusal has no step to carry it."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load
from ostler.qa.compile import Plan, Refusal, compile_plan_gaps

from conftest import write
from test_qa_compile import _API, _FLOW, _api_navigation, _flow_obligation, _navigation_context, _status, _step, _step_node

PAGE = "docs/features/acme/http/api.md"
FLOW = "docs/features/acme/flows/bill.md"

HEAD = """---
type: server
title: Bills API
---
# Bills API

- entry-url: http://example.com

## Endpoints

"""


def _server(repo: Path, *endpoints: str) -> None:
    write(repo / PAGE, HEAD + "\n".join(endpoints))


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _flow(*steps: str) -> str:
    listed = "\n".join(f"  - {step}" for step in steps)
    return f"""---
type: flow
title: Bill
---
# Bill

- start: [Bills API](../http/api.md)
- steps:
{listed}
- end: [Bills API](../http/api.md)
"""


def test_a_step_that_says_a_result_beside_its_link_is_refused(repo: Path) -> None:
    _server(repo, "### list-bills\n- method: GET\n- path: /bills\n- verify: http_status(code=200)\n- verify: json_path(path=\"$.id\", matches=\"x\")\n")
    write(repo / FLOW, _flow("[list-bills](../http/api.md#list-bills)",
                             "[list-bills](../http/api.md#list-bills) and the bill is paid"))
    [found] = _findings(repo, "step-claim")
    assert found.severity == "error"
    assert "step 2" in found.message and "and the bill is paid" in found.message


def test_a_step_of_two_links_and_no_words_is_clean(repo: Path) -> None:
    _server(repo, "### list-bills\n- method: GET\n- path: /bills\n- verify: http_status(code=200)\n- verify: json_path(path=\"$.id\", matches=\"x\")\n")
    write(repo / FLOW, _flow("[list-bills](../http/api.md#list-bills), [list-bills](../http/api.md#list-bills)"))
    assert _findings(repo, "step-claim") == []


STATUS_ONLY = "### list-bills\n- method: GET\n- path: /bills\n- verify: http_status(code=200)\n"


def test_an_outcome_that_checks_only_its_status_is_refused(repo: Path) -> None:
    _server(repo, STATUS_ONLY)
    [found] = _findings(repo, "status-only-outcome")
    assert found.severity == "error"
    assert "the 200 outcome checks only its status code" in found.message


def test_a_body_check_under_the_outcome_clears_it(repo: Path) -> None:
    _server(repo, STATUS_ONLY + "- verify: json_path(path=\"$.id\", matches=\"bill\")\n")
    assert _findings(repo, "status-only-outcome") == []


def test_a_bodyless_204_outcome_may_check_only_its_status(repo: Path) -> None:
    _server(repo, "### drop-bill\n- method: GET\n- path: /bills/old\n- verify: http_status(code=204)\n")
    assert _findings(repo, "status-only-outcome") == []


def test_a_refusal_arm_that_checks_only_its_status_is_refused_by_name(repo: Path) -> None:
    _server(repo, STATUS_ONLY + "- verify: json_path(path=\"$.id\", matches=\"bill\")\n"
            "- errors: 404 when the bill is missing\n  - verify: http_status(code=404)\n")
    [found] = _findings(repo, "status-only-outcome")
    assert "the 404 outcome" in found.message


WRITE = "- verify: http_status(code=200)\n- verify: json_path(path=\"$.id\", matches=\"bill\")\n"


def test_a_write_that_names_no_moves_is_refused(repo: Path) -> None:
    _server(repo, "### pay-bill\n- method: POST\n- path: /bills/pay\n" + WRITE)
    [found] = _findings(repo, "unstated-move")
    assert found.severity == "error"
    assert "a POST request changes what the server keeps" in found.message


def test_a_write_that_moves_none_because_it_only_validates_is_clean(repo: Path) -> None:
    _server(repo, "### pay-bill\n- method: POST\n- path: /bills/pay\n- moves: none, because it only validates\n" + WRITE)
    assert _findings(repo, "unstated-move") == []


def test_a_read_needs_no_moves(repo: Path) -> None:
    _server(repo, "### list-bills\n- method: GET\n- path: /bills\n" + WRITE)
    assert _findings(repo, "unstated-move") == []


def test_a_flows_own_refusal_status_compiles_no_scenario() -> None:
    oid = f"okf:{_FLOW}:end-state"
    node = f"{_API}#get-health"
    context = _navigation_context(
        _flow_obligation(oid, source=_FLOW, surface="api", steps=[_step(node, "endpoint", "api")],
                         checks=[_status(404)]),
        {**_step_node(node, {"route": ["GET /healthz"]}), "id": f"okf:{node}:up", "docPosition": [1, 0],
         "checksDeclared": [_status(200)]},
        navigation=_api_navigation(),
    )
    result = compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Refusal) and not isinstance(result, Plan)
    [gap] = [g for g in result.gaps if g.obligation_id == oid]
    assert gap.kind == "uncompilable-claim"
    assert gap.detail.startswith("a flow's verify: reads the response its last step gets")
    assert "drop the flow's http_status" in gap.detail
