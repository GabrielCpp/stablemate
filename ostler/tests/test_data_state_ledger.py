"""A flow step that applies only while a record is in a data state fails doctor unless the flow arranges that state."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write
from data_state_books import (API as BILLS_API, FIXTURE as BILLS_FIXTURE, FIXTURE_PAGE, FLOW as BILLS_FLOW, FLOW_PAGE,
                              PAY_MOVES, VOID_FROM_ISSUED, VOID_FROM_PAID, void_page)
from data_state_quota_books import API, FLOW, QUOTA_FIXTURE, QUOTA_FIXTURE_PAGE, REACHING_MOVES, flow_page, orders_page

USED_UP = "- fixture: [quota-used-up](../fixtures/quota-used-up.md)\n"
NO_FIXTURE = "- fixture: none, because nothing is arranged\n"


def _findings(repo: Path, *codes: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code in codes]


def _quota(repo: Path, steps: tuple[str, ...], fixture: str, create_moves: str = "") -> None:
    write(repo / API, orders_page(create_moves))
    write(repo / QUOTA_FIXTURE, QUOTA_FIXTURE_PAGE)
    write(repo / FLOW, flow_page(steps, fixture))


def test_a_case_that_needs_a_state_no_fixture_arranges_fails_and_names_the_case_and_the_state(repo: Path) -> None:
    _quota(repo, ("over-quota",), NO_FIXTURE)
    [found] = _findings(repo, "unheld-condition")
    assert found.severity == "error"
    assert "step 1" in found.message
    assert "over-quota" in found.message
    assert "quota-reached" in found.message
    assert "quota-used-up" in found.message
    assert found.path == FLOW


def test_the_finding_names_the_state_the_ledger_holds(repo: Path) -> None:
    _quota(repo, ("create-order", "over-quota"), NO_FIXTURE, "- moves: to [Quota open](#quota-open)\n")
    [found] = _findings(repo, "unheld-condition")
    assert "step 2" in found.message
    assert "`quota-open`" in found.message


def test_a_case_that_needs_a_state_the_flow_names_a_fixture_for_is_clean(repo: Path) -> None:
    _quota(repo, ("over-quota",), USED_UP)
    assert _findings(repo, "unheld-condition") == []


def test_a_case_that_needs_a_state_an_earlier_step_moves_the_record_to_is_clean(repo: Path) -> None:
    _quota(repo, ("create-order", "over-quota"), NO_FIXTURE, REACHING_MOVES)
    assert _findings(repo, "unheld-condition") == []


def test_a_case_before_the_step_that_moves_the_record_fails(repo: Path) -> None:
    _quota(repo, ("over-quota", "create-order"), NO_FIXTURE, REACHING_MOVES)
    [found] = _findings(repo, "unheld-condition")
    assert "step 1" in found.message


def _bills(repo: Path, steps: tuple[str, ...], void_moves: str) -> None:
    write(repo / BILLS_API, void_page(void_moves=void_moves, pay_moves=PAY_MOVES))
    write(repo / BILLS_FIXTURE, FIXTURE_PAGE)
    write(repo / BILLS_FLOW, FLOW_PAGE.replace(
        "  - [create-bill](../http/api.md#create-bill)\n  - [pay-bill](../http/api.md#pay-bill)\n",
        "".join(f"  - [{step}](../http/api.md#{step})\n" for step in steps)))


def test_a_move_out_of_a_state_the_ledger_does_not_hold_fails(repo: Path) -> None:
    _bills(repo, ("create-bill", "pay-bill", "void-bill"), VOID_FROM_ISSUED)
    [found] = _findings(repo, "unheld-condition")
    assert "step 3" in found.message
    assert "void-bill" in found.message
    assert "`bill-issued`" in found.message
    assert "`bill-paid`" in found.message


def test_a_move_out_of_the_state_the_ledger_holds_is_clean(repo: Path) -> None:
    _bills(repo, ("create-bill", "pay-bill", "void-bill"), VOID_FROM_PAID)
    assert _findings(repo, "unheld-condition") == []


def test_a_move_out_of_a_state_nothing_has_set_is_not_flagged(repo: Path) -> None:
    _bills(repo, ("void-bill",), VOID_FROM_ISSUED)
    assert _findings(repo, "unheld-condition") == []


def test_a_when_that_links_no_data_state_stays_prose(repo: Path) -> None:
    _quota(repo, ("over-quota",), NO_FIXTURE)
    page = (repo / API).read_text(encoding="utf-8").replace(
        "- when: [Quota reached](#quota-reached)", "- when: the account is over its quota")
    write(repo / API, page)
    assert _findings(repo, "unheld-condition") == []
