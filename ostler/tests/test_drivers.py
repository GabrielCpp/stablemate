"""`drivers.DRIVERS` joined back to every table it is the vocabulary for.

One home for all five joins, rather than splitting the doc joins into their own file and the
table joins into `test_routes.py`/`test_acts.py`: they are one question asked of five
different tables — does this table answer for every §4.1 value? — and reading them together
makes that visible in a way scattering them across three files would not.
"""

from __future__ import annotations

import re

from pathlib import Path

from ostler import acts, drivers, routes


def _table_row_values() -> list[str]:
    """The backtick-quoted values of §4.1's `driver` row in `docs/okf-runbook.md`.

    Located the way `test_doctor.py::_documented_codes` locates `doctor-codes.md`: a fixed
    path down from this test file, not a search, so a moved or renamed doc breaks loudly.
    """
    page = Path(__file__).resolve().parents[2] / "ostler/docs/okf-runbook.md"
    [row] = re.findall(r"^\| `driver` \|(.+)\|$", page.read_text(), re.M)
    return re.findall(r"`([a-z]+)`", row)


def test_the_runbook_lists_every_driver_value_drivers_declares() -> None:
    """§4.1's `driver` row and `drivers.DRIVERS` must name the same set.

    Neither side is allowed to lead: a value added to the doc and not this tuple would leave
    every table in this package silently short a row, and a value added to the tuple and not
    the doc would let code accept a spelling no author was ever told about. Asserting set
    equality both ways, rather than containment, is what makes that drift visible instead of
    tolerated.
    """
    parsed = _table_row_values()
    assert parsed, "the §4.1 `driver` row parsed no values at all — the regex found nothing"
    assert set(parsed) == set(drivers.DRIVERS)


def _node_type_page_row_values() -> list[str]:
    """The backtick-quoted values of the `driver` row on the `runbook` node-type page.

    The **library source** under `base-library/`, not the `.claude/` copy `make agent-install`
    generates from it: a test that read the generated mirror would pass on a tree whose source
    had drifted and only fail after somebody regenerated.
    """
    page = (Path(__file__).resolve().parents[2]
            / "base-library/library/skills/ostler/okf/references/node-types/runbook.md")
    [row] = re.findall(r"^\| `driver` \|(.+)\|$", page.read_text(), re.M)
    return re.findall(r"`([a-z]+)`", row)


def test_the_node_type_page_lists_every_driver_value_drivers_declares() -> None:
    """The `runbook` node-type page states the vocabulary a fourth time, and it is the copy a
    book author actually reads — the §4.1 table is ostler's own runbook, and the skill page is
    what ships to the agent writing the book. An author held to a list the code does not
    enforce, or free of one it does, is the drift this join exists to make loud.
    """
    parsed = _node_type_page_row_values()
    assert parsed, "the node-type page's `driver` row parsed no values at all"
    assert set(parsed) == set(drivers.DRIVERS)


def test_route_grammar_names_every_driver() -> None:
    """A §4.1 value `ROUTE_GRAMMAR` does not name falls through to the path-addressed default —
    the wrong answer for a driver that has in fact declared it addresses nothing by path. A new
    or removed §4.1 value must be answered by a row here, not silently inherit the fallback.
    """
    assert set(routes.ROUTE_GRAMMAR) == set(drivers.DRIVERS)


def test_surface_performable_types_names_every_driver() -> None:
    """A §4.1 value `SURFACE_PERFORMABLE_TYPES` does not name reads as performing against no
    surface at all, by the table's default rather than by a stated row — the same silent-gap
    failure mode `ROUTE_GRAMMAR`'s join guards against, for the table that says which node
    *type* a driver can exercise.
    """
    assert set(routes.SURFACE_PERFORMABLE_TYPES) == set(drivers.DRIVERS)


def test_acts_accounts_for_every_driver_used_or_omitted() -> None:
    """Every §4.1 value either performs at least one act in `ACTS`, or is named in
    `ACT_DRIVER_OMISSIONS` with a reason it performs none — and never both. A new §4.1 value
    that is wired into neither would silently perform nothing, with no declaration anywhere
    saying that was on purpose.
    """
    used = {driver for spec in acts.ACTS for driver in spec.drivers}
    omitted = set(acts.ACT_DRIVER_OMISSIONS)

    assert used | omitted == set(drivers.DRIVERS)
    assert used & omitted == set()
    assert all(reason.strip() for reason in acts.ACT_DRIVER_OMISSIONS.values())
