"""A server page declares passages of endpoint steps: doctor refuses a passage taken before the walk holds what it sends."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

API = "docs/features/acme/http/api.md"
FLOW = "docs/features/acme/flows/bill.md"
FIXTURE = "docs/features/acme/fixtures/seeded-bills.md"

API_PAGE = """---
type: server
title: Bills API
---
# Bills API

- entry-url: http://example.com

## Endpoints

### create-bill
- method: POST
- path: /bills
- capture: bill_id from $.id
- verify: http_status(code=201)

### issue-bill
- method: POST
- path: /bills/{bill_id}/issue
- verify: http_status(code=200)

### pay-bill
- method: POST
- path: /bills/{bill_id}/pay
- verify: http_status(code=200)

## Passages

### Issue a bill

- steps:
  - [create-bill](#create-bill)
  - [issue-bill](#issue-bill)

### Pay a bill

- steps:
  - [pay-bill](#pay-bill)
"""

FIXTURE_PAGE = """---
type: fixture
title: Seeded bills
---
# Seeded bills

- provides:
  - bill_id — the id of a bill on file

## Steps

### seed-it
- kind: seed
- run: ./scripts/seed-bills.sh
"""


def flow_page(*steps: str, fixture: str = "") -> str:
    listed = "\n".join(f"  - [{label}]({href})" for label, href in (step.split("|") for step in steps))
    arranged = "- fixture: [Seeded bills](../fixtures/seeded-bills.md)\n" if fixture else ""
    return f"""---
type: flow
title: Bill
---
# Bill

- start: [Bills API](../http/api.md)
{arranged}- steps:
{listed}
- end: [Bills API](../http/api.md)
"""


CREATE = "create-bill|../http/api.md#create-bill"
ISSUE_PASSAGE = "Issue a bill|../http/api.md#issue-a-bill"
PAY_PASSAGE = "Pay a bill|../http/api.md#pay-a-bill"


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _book(repo: Path, flow: str, *, fixture: bool = False) -> None:
    write(repo / API, API_PAGE)
    write(repo / FLOW, flow)
    if fixture:
        write(repo / FIXTURE, FIXTURE_PAGE)


def test_a_server_passage_taken_before_the_walk_holds_its_value_breaks_the_joint(repo: Path) -> None:
    _book(repo, flow_page(PAY_PASSAGE))
    [found] = _findings(repo, "broken-joint")
    assert found.severity == "error"
    assert "{bill_id}" in found.message and "step 1" in found.message
    assert f"{API}#pay-a-bill" in found.message


def test_a_server_passage_taken_after_the_step_that_captures_its_value_is_clean(repo: Path) -> None:
    _book(repo, flow_page(CREATE, PAY_PASSAGE))
    assert _findings(repo, "broken-joint") == []


def test_a_server_passage_that_captures_its_own_value_is_clean(repo: Path) -> None:
    _book(repo, flow_page(ISSUE_PASSAGE))
    assert _findings(repo, "broken-joint") == []


def test_moving_a_passage_ahead_of_the_step_that_captures_its_id_fails(repo: Path) -> None:
    _book(repo, flow_page(CREATE, PAY_PASSAGE))
    assert _findings(repo, "broken-joint") == []
    write(repo / FLOW, flow_page(PAY_PASSAGE, CREATE))
    [found] = _findings(repo, "broken-joint")
    assert "{bill_id}" in found.message


def test_a_fixture_the_flow_names_holds_the_value_a_passage_sends(repo: Path) -> None:
    _book(repo, flow_page(PAY_PASSAGE, fixture="seeded-bills"), fixture=True)
    assert _findings(repo, "broken-joint") == []


def test_two_flows_may_share_one_server_passage(repo: Path) -> None:
    _book(repo, flow_page(ISSUE_PASSAGE))
    write(repo / "docs/features/acme/flows/bill-again.md", flow_page(ISSUE_PASSAGE, PAY_PASSAGE))
    assert _findings(repo, "broken-joint") == []


def test_a_passages_section_on_a_server_page_is_in_place(repo: Path) -> None:
    _book(repo, flow_page(CREATE, PAY_PASSAGE))
    assert _findings(repo, "misplaced-section") == []


def test_a_passages_section_on_a_flow_page_is_still_misplaced(repo: Path) -> None:
    _book(repo, flow_page(CREATE, PAY_PASSAGE))
    write(repo / FLOW, flow_page(CREATE, PAY_PASSAGE)
          + "\n## Passages\n\n### Pay again\n\n- steps:\n  - [pay-bill](../http/api.md#pay-bill)\n")
    assert len(_findings(repo, "misplaced-section")) == 1
