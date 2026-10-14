"""A screen state that settles only while a record is in a data state fails doctor unless the walk puts the record there."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write
from data_state_books import (FIXTURE, FIXTURE_PAGE, ISSUED_ARRANGED, PAID, PAY_MOVES, api_page)

SCREEN = "docs/features/acme/web/screens/bill.md"
FLOW = "docs/features/acme/flows/see-a-bill-paid.md"
FIXTURE_STEP = "- fixture: [issued-bill](../fixtures/issued-bill.md)\n"

SCREEN_PAGE = """---
type: screen
title: Bill
---
# Bill

- route: /bills/{{bill_id}}
- requires: none
- params: none

## Components

### Pay button
- role: button
- name: Pay

### Unpaid banner
- role: status
- name: Unpaid

### Paid banner
- role: status
- name: Paid

## Interactions

### pay-click
- on: [Pay button](#pay-button)
- trigger: click
- role: button
- name: Pay
- keyboard: Tab to focus, Enter to activate
{sends}- does: pays the bill

## Screen states

### Unpaid
{unpaid_when}- shows:
  - [Unpaid banner](#unpaid-banner)
  - [Paid banner](#paid-banner) absent

### Paid
{paid_when}- shows:
  - [Paid banner](#paid-banner)
  - [Unpaid banner](#unpaid-banner) absent

## Passages

### Pay it
- from: [Unpaid](#unpaid)
- steps:
  - [pay-click](#pay-click)
- to: [Paid](#paid)
"""

WHEN_ISSUED = "- when: [Bill issued](../../http/api.md#bill-issued)\n"
WHEN_PAID = "- when: [Bill paid](../../http/api.md#bill-paid)\n"
SENDS_PAY = "- sends: [pay-bill](../../http/api.md#pay-bill)\n"

UNPAID = "[Unpaid](../web/screens/bill.md#unpaid)"
CLICK = "[pay-click](../web/screens/bill.md#pay-click)"
PAID_STOP = "[Paid](../web/screens/bill.md#paid)"
PASSAGE = "[Pay it](../web/screens/bill.md#pay-it)"


def _flow(steps: tuple[str, ...], fixture: str) -> str:
    listed = "".join(f"  - {step}\n" for step in steps)
    return f"""---
type: flow
title: See a bill paid
---
# See a bill paid

- start: [Bill](../web/screens/bill.md)
{fixture}- steps:
{listed}- end: [Bill](../web/screens/bill.md)
"""


def _book(repo: Path, steps: tuple[str, ...], *, fixture: str = FIXTURE_STEP, sends: str = SENDS_PAY,
          unpaid_when: str = WHEN_ISSUED, paid_when: str = WHEN_PAID) -> None:
    states = ISSUED_ARRANGED + "\n" + PAID
    write(repo / "docs/features/acme/http/api.md", api_page(states=states, pay_moves=PAY_MOVES))
    write(repo / FIXTURE, FIXTURE_PAGE)
    write(repo / SCREEN, SCREEN_PAGE.format(sends=sends, unpaid_when=unpaid_when, paid_when=paid_when))
    write(repo / FLOW, _flow(steps, fixture))


def _findings(repo: Path, *codes: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code in codes]


def test_a_flow_that_clicks_pay_before_the_paid_stop_is_clean(repo: Path) -> None:
    _book(repo, (UNPAID, CLICK, PAID_STOP))
    assert _findings(repo, "unheld-condition") == []


def test_the_same_flow_without_the_click_fails_at_the_paid_stop(repo: Path) -> None:
    _book(repo, (UNPAID, PAID_STOP))
    [found] = _findings(repo, "unheld-condition")
    assert found.severity == "error"
    assert found.path == FLOW
    assert found.message.startswith(
        f"{FLOW}: step 2 stops at `paid`, which the screen settles in only while the bill is `bill-paid`, "
        "and the walk holds `bill-issued` there. ")
    assert "an earlier step that moves the bill to `bill-paid`" in found.message


def test_a_stop_whose_state_has_no_when_is_never_flagged(repo: Path) -> None:
    _book(repo, (UNPAID, PAID_STOP), paid_when="")
    assert _findings(repo, "unheld-condition") == []


def test_a_flow_with_no_fixture_that_stops_at_paid_is_flagged(repo: Path) -> None:
    _book(repo, (PAID_STOP,), fixture="- fixture: none, because nothing is arranged\n")
    [found] = _findings(repo, "unheld-condition")
    assert "step 1 stops at `paid`" in found.message
    assert "no state of the bill" in found.message


def test_a_screen_passage_whose_interactions_send_pay_bill_is_clean(repo: Path) -> None:
    _book(repo, (UNPAID, PASSAGE))
    assert _findings(repo, "unheld-condition") == []


def test_a_screen_passage_whose_interactions_send_nothing_fails_at_its_end(repo: Path) -> None:
    _book(repo, (UNPAID, PASSAGE), sends="")
    [found] = _findings(repo, "unheld-condition")
    assert "step 2 stops at `paid`" in found.message


def test_a_sends_link_that_lands_on_a_component_is_a_finding(repo: Path) -> None:
    _book(repo, (UNPAID, CLICK, PAID_STOP), sends="- sends: [Pay button](#pay-button)\n")
    [found] = _findings(repo, "moves-shape")
    assert "`sends:`" in found.message
    assert "no endpoint or invocation" in found.message


def test_a_when_link_that_lands_on_a_non_data_state_is_a_finding(repo: Path) -> None:
    _book(repo, (UNPAID, CLICK, PAID_STOP), paid_when="- when: [pay-bill](../../http/api.md#pay-bill)\n")
    [found] = _findings(repo, "data-state-shape")
    assert "`when:`" in found.message
    assert "no data state" in found.message
