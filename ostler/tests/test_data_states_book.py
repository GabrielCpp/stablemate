"""A server page declares data states and the moves between them: doctor refuses what a walk could not read back."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write
from data_state_books import API, ENDPOINTS, FIXTURE, FIXTURE_PAGE, ISSUED, PAID, PAY_MOVES, api_page


def _findings(repo: Path, *codes: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code in codes]


def _book(repo: Path, **page: str) -> None:
    write(repo / API, api_page(**page))
    write(repo / FIXTURE, FIXTURE_PAGE)


def test_a_lifecycle_of_two_states_that_expect_different_values_is_clean(repo: Path) -> None:
    _book(repo, pay_moves=PAY_MOVES)
    assert _findings(repo, "indistinct-states", "moves-shape", "data-state-shape", "misplaced-section") == []


def test_two_sibling_states_that_expect_the_same_value_of_one_field_are_indistinct(repo: Path) -> None:
    _book(repo, states=ISSUED + "\n" + PAID.replace('equals="paid"', 'equals="issued"'))
    [found] = _findings(repo, "indistinct-states")
    assert found.severity == "error"
    assert "bill-issued" in found.message and "bill-paid" in found.message
    assert found.path == API


def test_sibling_states_that_check_different_fields_are_indistinct(repo: Path) -> None:
    _book(repo, states=ISSUED + "\n" + PAID.replace('path="$.status"', 'path="$.paid_at"'))
    assert len(_findings(repo, "indistinct-states")) == 1


def test_states_of_different_records_are_not_siblings(repo: Path) -> None:
    _book(repo, states=ISSUED + "\n" + PAID.replace('equals="paid"', 'equals="issued"').replace("of: bill", "of: receipt"))
    assert _findings(repo, "indistinct-states") == []


def test_states_that_observe_different_endpoints_are_treated_as_told_apart(repo: Path) -> None:
    endpoints = ENDPOINTS + "\n### get-receipt\n- method: GET\n- path: /bills/{bill_id}/receipt\n- verify: http_status(code=200)\n"
    other = PAID.replace('equals="paid"', 'equals="issued"').replace("#get-bill", "#get-receipt")
    _book(repo, endpoints=endpoints, states=ISSUED + "\n" + other)
    assert _findings(repo, "indistinct-states") == []


def test_a_move_naming_a_screen_state_is_refused(repo: Path) -> None:
    write(repo / "docs/features/acme/screens/bills.md", """---
type: screen
title: Bills
---
# Bills

## Screen states

### Loaded
- shows: nothing
""")
    _book(repo, pay_moves="- moves: [Bill issued](#bill-issued) to [Loaded](../screens/bills.md#loaded)\n")
    [found] = _findings(repo, "moves-shape")
    assert "no data state" in found.message and "loaded" in found.message


def test_a_move_between_states_of_different_records_is_refused(repo: Path) -> None:
    _book(repo, states=ISSUED + "\n" + PAID.replace("of: bill", "of: receipt"), pay_moves=PAY_MOVES)
    [found] = _findings(repo, "moves-shape")
    assert "bill" in found.message and "receipt" in found.message


def test_a_move_that_matches_none_of_the_three_spellings_is_refused(repo: Path) -> None:
    _book(repo, pay_moves="- moves: issued then paid\n")
    [found] = _findings(repo, "moves-shape")
    assert "three spellings" in found.message


def test_the_landing_only_and_none_spellings_are_clean(repo: Path) -> None:
    _book(repo, pay_moves="- moves: to [Bill paid](#bill-paid)\n- moves: none, because the call only audits\n")
    assert _findings(repo, "moves-shape") == []


def test_data_states_on_a_page_that_is_not_a_server_or_cli_page_are_misplaced(repo: Path) -> None:
    write(repo / "docs/features/acme/screens/bills.md", f"""---
type: screen
title: Bills
---
# Bills

## Screen states

### Loaded
- shows: nothing

## Data states

{ISSUED}""")
    [found] = _findings(repo, "misplaced-section")
    assert "Data states" in found.message or "data-state" in found.message


def test_an_observe_that_links_no_endpoint_is_refused(repo: Path) -> None:
    _book(repo, states=ISSUED.replace("(#get-bill)", "(#bill-issued)") + "\n" + PAID)
    [found] = _findings(repo, "data-state-shape")
    assert "observe" in found.message


def test_an_of_that_is_not_one_plain_word_is_refused(repo: Path) -> None:
    _book(repo, states=ISSUED.replace("of: bill", "of: a bill record") + "\n" + PAID)
    [found] = _findings(repo, "data-state-shape")
    assert "of" in found.message


def test_a_fixture_that_resolves_is_clean_and_one_that_does_not_is_a_broken_link(repo: Path) -> None:
    with_fixture = ISSUED + "- fixture: [Issued bill](../fixtures/issued-bill.md)\n"
    _book(repo, states=with_fixture + "\n" + PAID)
    assert [f for f in doctor.run(load(repo)).findings if "issued-bill" in f.message] == []
    _book(repo, states=with_fixture.replace("issued-bill.md", "missing.md") + "\n" + PAID)
    assert [f for f in doctor.run(load(repo)).findings if "missing.md" in f.message]
