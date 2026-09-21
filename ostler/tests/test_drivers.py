"""`drivers.DRIVERS` joined back to every table it is the vocabulary for."""

from __future__ import annotations

import re

from pathlib import Path

from ostler import acts, drivers, routes


def _table_row_values() -> list[str]:
    """The backtick-quoted values of §4.1's `driver` row in `docs/okf-runbook.md`."""
    page = Path(__file__).resolve().parents[2] / "ostler/docs/okf-runbook.md"
    [row] = re.findall(r"^\| `driver` \|(.+)\|$", page.read_text(), re.M)
    return re.findall(r"`([a-z]+)`", row)


def test_the_runbook_lists_every_driver_value_drivers_declares() -> None:
    """§4.1's `driver` row and `drivers.DRIVERS` must name the same set."""
    parsed = _table_row_values()
    assert parsed, "the §4.1 `driver` row parsed no values at all — the regex found nothing"
    assert set(parsed) == set(drivers.DRIVERS)


def _node_type_page_row_values() -> list[str]:
    """The backtick-quoted values of the `driver` row on the `runbook` node-type page."""
    page = (Path(__file__).resolve().parents[2]
            / "base-library/library/skills/ostler/okf/references/node-types/runbook.md")
    [row] = re.findall(r"^\| `driver` \|(.+)\|$", page.read_text(), re.M)
    return re.findall(r"`([a-z]+)`", row)


def test_the_node_type_page_lists_every_driver_value_drivers_declares() -> None:
    """The `runbook` node-type page states the vocabulary a fourth time, and it is the copy a book author actually reads — the §4.1 table is ostler's own runbook, and the skill page is what ships to the agent writing the book."""
    parsed = _node_type_page_row_values()
    assert parsed, "the node-type page's `driver` row parsed no values at all"
    assert set(parsed) == set(drivers.DRIVERS)


def test_route_grammar_names_every_driver() -> None:
    """A §4.1 value `ROUTE_GRAMMAR` does not name falls through to the path-addressed default — the wrong answer for a driver that has in fact declared it addresses nothing by path."""
    assert set(routes.ROUTE_GRAMMAR) == set(drivers.DRIVERS)


def test_surface_performable_types_names_every_driver() -> None:
    """A §4.1 value `SURFACE_PERFORMABLE_TYPES` does not name reads as performing against no surface at all, by the table's default rather than by a stated row — the same silent-gap failure mode `ROUTE_GRAMMAR`'s join guards against, for the table that says which node *type* a driver can exercise."""
    assert set(routes.SURFACE_PERFORMABLE_TYPES) == set(drivers.DRIVERS)


def test_acts_accounts_for_every_driver_used_or_omitted() -> None:
    """Every §4.1 value either performs at least one act in `ACTS`, or is named in `ACT_DRIVER_OMISSIONS` with a reason it performs none — and never both."""
    used = {driver for spec in acts.ACTS for driver in spec.drivers}
    omitted = set(acts.ACT_DRIVER_OMISSIONS)

    assert used | omitted == set(drivers.DRIVERS)
    assert used & omitted == set()
    assert all(reason.strip() for reason in acts.ACT_DRIVER_OMISSIONS.values())
