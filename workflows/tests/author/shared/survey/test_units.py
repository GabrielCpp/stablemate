"""`select_next_unit` and `mark_unit` — the survey's loop, which keeps no state of its
own: the inventory file and the finding records *are* the loop state.

That is the property these tests are about. Selection is deterministic and driven only by
what is on disk, an empty pending set is the coverage proof rather than a counter, and
marking never wedges the loop — a missing or invalid record becomes a durable `blocked`
gap that `verify_records` re-surfaces at the gate.

Ported from `surveyor/scripts/{select-next-unit,mark-unit}.py`, and shared verbatim by the
parity surveyor.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse_workflows.author.shared.survey import mark_unit, select_next_unit

Write = Callable[[Path, str], Path]
WriteJson = Callable[[Path, Any], Path]
ReadJson = Callable[[Path], Any]

INVENTORY = "docs/survey/inventory.json"
FINDINGS = "docs/survey/findings"


def _unit(unit_id: str, status: str = "pending", kind: str = "folder") -> dict:
    return {"id": unit_id, "path": unit_id, "kind": kind, "status": status}


def _record(unit_id: str, status: str) -> str:
    return (
        f"---\ntype: survey-finding\nunit: {unit_id}\nstatus: {status}\n---\n\n"
        f"# Survey finding: {unit_id}\n"
    )


# ---------------------------------------------------------------------- selection


def test_the_first_pending_unit_is_the_one_selected(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(
        repo / INVENTORY,
        {
            "units": [
                _unit("src/api", "assessed"),
                _unit("src/web"),
                _unit("src/cli"),
            ]
        },
    )

    pick = select_next_unit(logger)

    assert pick.has_unit is True
    assert pick.unit_id == "src/web"
    assert pick.unit_path == "src/web"
    assert pick.unit_kind == "folder"
    # The record path is derived once, here, so assess/validate/mark all agree on it
    # without three copies of the slug rule.
    assert pick.record_path == f"{FINDINGS}/src-web.md"
    assert pick.progress == "1/3"


def test_done_and_blocked_units_are_both_skipped(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """`assessed` and `clean` are the two done-states; `blocked` is set aside rather than
    retried, and stays an open gap for the coverage gate."""
    write_json(
        repo / INVENTORY,
        {
            "units": [
                _unit("a", "clean"),
                _unit("b", "blocked"),
                _unit("c", "assessed"),
                _unit("d"),
            ]
        },
    )

    pick = select_next_unit(logger)

    assert pick.unit_id == "d"


def test_an_empty_pending_set_is_the_coverage_proof(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """Structural rather than post-hoc: the loop ends because nothing is left, not
    because a budget ran out."""
    write_json(repo / INVENTORY, {"units": [_unit("a", "assessed"), _unit("b", "blocked")]})

    pick = select_next_unit(logger)

    assert pick.has_unit is False
    assert pick.unit_id == ""
    assert "no pending units left" in pick.reason
    # A blocked unit ends the loop but does not count as progress — it is an open gap
    # until an operator re-pends it, and the coverage gate says so out loud.
    assert pick.progress == "1/2"


def test_a_missing_inventory_is_reported_not_raised(
    repo: Path, logger: logging.Logger
) -> None:
    """The flow reads `has_unit` and moves to the coverage gate, where the missing
    inventory becomes a verify finding — the loop does not crash on it."""
    pick = select_next_unit(logger)

    assert pick.has_unit is False
    assert "no inventory" in pick.reason


def test_an_unparseable_inventory_leaves_it_to_verify_records(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / INVENTORY, "{ nope\n")

    pick = select_next_unit(logger)

    assert pick.has_unit is False
    assert "not parseable" in pick.reason


def test_the_findings_directory_travels_with_the_parameter(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """The parity surveyor runs the same node under its own survey dir."""
    inventory = "docs/survey/legacy-vs-new/inventory.json"
    write_json(repo / inventory, {"units": [_unit("legacy/reports/q1")]})

    pick = select_next_unit(
        logger, inventory=inventory, findings_dir="docs/survey/legacy-vs-new/findings"
    )

    assert pick.record_path == "docs/survey/legacy-vs-new/findings/legacy-reports-q1.md"


# ------------------------------------------------------------------------ marking


def test_a_unit_is_marked_with_its_records_own_status(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    """The record is the source of truth, not the node's parameters: an assessor that
    found nothing writes `clean`, and the inventory follows."""
    write_json(repo / INVENTORY, {"units": [_unit("src/web")]})
    write(repo / FINDINGS / "src-web.md", _record("src/web", "clean"))

    result = mark_unit(logger, INVENTORY, "src/web", f"{FINDINGS}/src-web.md")

    assert result.marked is True
    assert result.unit_status == "clean"
    assert read_json(repo / INVENTORY)["units"][0]["status"] == "clean"


def test_a_missing_record_becomes_a_blocked_stub_rather_than_a_wedge(
    repo: Path, logger: logging.Logger, write_json: WriteJson, read_json: ReadJson
) -> None:
    """The give-up path. A unit whose assessment produced nothing must not stall the
    survey — the gap is written down, the unit is blocked, and the loop moves on."""
    write_json(repo / INVENTORY, {"units": [_unit("src/web")]})

    result = mark_unit(
        logger,
        INVENTORY,
        "src/web",
        f"{FINDINGS}/src-web.md",
        fallback="assessor ran out of context",
    )

    assert result.marked is True
    assert result.unit_status == "blocked"
    assert "wrote a blocked stub" in result.mark_note
    stub = (repo / FINDINGS / "src-web.md").read_text(encoding="utf-8")
    assert "status: blocked" in stub
    # The reason is durable, in the record, where the coverage gate reads it.
    assert "assessor ran out of context" in stub
    assert read_json(repo / INVENTORY)["units"][0]["status"] == "blocked"


def test_an_invalid_record_blocks_the_unit_without_overwriting_it(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    """Whatever the assessor did write is evidence for the operator, so the node marks
    the unit blocked and leaves the file alone."""
    write_json(repo / INVENTORY, {"units": [_unit("src/web")]})
    write(repo / FINDINGS / "src-web.md", "no front matter at all\n")

    result = mark_unit(logger, INVENTORY, "src/web", f"{FINDINGS}/src-web.md")

    assert result.unit_status == "blocked"
    assert "record exists but is invalid" in result.mark_note
    assert (repo / FINDINGS / "src-web.md").read_text(encoding="utf-8") == (
        "no front matter at all\n"
    )
    assert read_json(repo / INVENTORY)["units"][0]["status"] == "blocked"


def test_a_record_with_a_status_outside_the_vocabulary_is_invalid(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/web")]})
    write(repo / FINDINGS / "src-web.md", _record("src/web", "mostly-fine"))

    result = mark_unit(logger, INVENTORY, "src/web", f"{FINDINGS}/src-web.md")

    assert result.unit_status == "blocked"


def test_marking_a_unit_the_inventory_does_not_carry_is_reported(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """A split parent, most likely — the status still comes back so the flow can log it,
    but `marked` is false and the run does not claim a write that did not happen."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})
    write(repo / FINDINGS / "src-web.md", _record("src/web", "assessed"))

    result = mark_unit(logger, INVENTORY, "src/web", f"{FINDINGS}/src-web.md")

    assert result.marked is False
    assert result.unit_status == "assessed"
    assert "not found" in result.mark_note


def test_marking_needs_all_three_of_its_arguments(
    repo: Path, logger: logging.Logger
) -> None:
    result = mark_unit(logger, "", "src/web", f"{FINDINGS}/src-web.md")

    assert result.marked is False
    assert "all required" in result.mark_note


def test_a_missing_inventory_reports_the_status_it_would_have_written(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-web.md", _record("src/web", "assessed"))

    result = mark_unit(logger, INVENTORY, "src/web", f"{FINDINGS}/src-web.md")

    assert result.marked is False
    assert result.unit_status == "assessed"
    assert "could not be read" in result.mark_note
