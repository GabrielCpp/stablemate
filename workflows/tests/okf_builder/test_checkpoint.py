"""The convergence gate's scoping and its severity blindness (`shared/checkpoint.py`).

`test_workflow.py` drives the gate end to end and asserts what the loop *does* with a dirty
book. What is asserted here is what the gate counts as dirty in the first place, because that
is the question the whole backfill turns on: the codes deciding whether a book's claims can
ever be observed — `undeclared-obligation`, `compound-normative-bullet`, `weak-check`,
`unstated-precondition` — are all warns, so an error-only gate converges happily on a book in
which nothing is falsifiable.

`scoped_findings` is exercised against literal report dicts rather than through `doctor`.
The filter is about severity, the waiver stamp and the path prefix, and doctor is not the
thing under test — a fixture book able to produce every combination on demand would be a
larger fiction than the three-key dicts it would be standing in for.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_builder.shared.checkpoint import (
    checkpoint_book,
    scoped_error_findings,
    scoped_findings,
)

BOOK = "docs/features/acme"


def _report(*findings: dict) -> dict:
    return {"findings": list(findings)}


def _finding(code: str, severity: str = "warn", *, path: str = f"{BOOK}/a.md",
             waived: bool = False) -> dict:
    return {"severity": severity, "code": code, "path": path, "waived": waived,
            "ref": f"{path}#node", "line": 1}


def test_a_warning_is_a_standing_finding() -> None:
    """The gate's whole widening in one assertion.

    `undeclared-obligation` is a warn, and it is the finding that says a node's claims reach
    QA with nothing to bind. A gate that dropped it would call a book converged precisely
    when its obligations became unprovable.
    """
    report = _report(_finding("undeclared-obligation"))
    assert [f["code"] for f in scoped_findings(report, "/repo", "")] == [
        "undeclared-obligation"]
    assert scoped_error_findings(report, "/repo", "") == []


def test_a_waived_finding_leaves_the_gate() -> None:
    """Waiving is the one exit, and it is the one that records a reason in the book.

    `doctor._apply_waivers` demotes to `warn` *and* stamps `waived: true`. Reading the stamp
    rather than the severity is what keeps a warn that nobody waived inside the gate while
    letting an adjudicated one out.
    """
    report = _report(
        _finding("ambiguous-locator", "warn", waived=True),
        _finding("compound-normative-bullet"),
    )
    assert [f["code"] for f in scoped_findings(report, "/repo", "")] == [
        "compound-normative-bullet"]


def test_a_waived_error_leaves_the_gate_too() -> None:
    """A waiver a doctor profile left at error severity still exits.

    The stamp is the decision; the severity it happens to carry afterwards is not a second
    vote. A gate that re-admitted a waived error would make the waivers file unable to
    unstick the loop it exists to unstick.
    """
    report = _report(_finding("missing-code-symbol", "error", waived=True))
    assert scoped_findings(report, "/repo", "") == []


def test_findings_outside_the_book_are_not_this_run_s_problem(tmp_path: Path) -> None:
    """A monorepo's unrelated books cannot be repaired by a run scoped to one of them.

    Widening from errors to every finding widens this exposure too: the sibling books' warns
    now vastly outnumber their errors, so the scope test is doing more work than it was.
    """
    (tmp_path / BOOK).mkdir(parents=True)
    report = _report(
        _finding("undeclared-obligation", path=f"{BOOK}/mine.md"),
        _finding("undeclared-obligation", path="docs/features/globex/theirs.md"),
        # A prefix must match on a path segment, not on characters: `docs/features/acme-legacy`
        # is a different book that a naive `startswith` would drag into this run.
        _finding("undeclared-obligation", path="docs/features/acme-legacy/theirs.md"),
    )
    kept = scoped_findings(report, str(tmp_path), str(tmp_path / BOOK))
    assert [f["path"] for f in kept] == [f"{BOOK}/mine.md"]


def test_a_book_with_warnings_and_no_errors_is_dirty(
    booked: Path, write: Callable[[Path, str], Path], logger: logging.Logger
) -> None:
    """The gate, end to end, on the case the error-only version called finished.

    `booked` is doctor-green. Adding one method whose normative bullet declares no check
    leaves the book at zero errors and one warn — which is the exact state a book written
    before the current contract is in, at scale.
    """
    write(
        booked / "docs/features/acme/concepts/charge.md",
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n- code: `acme/service.py::charge`\n\nCharging.\n\n"
        "## Methods\n\n### apply\n\n- sig: `charge(amount) -> dict`\n"
        "- returns: the receipt it creates under the payer's name\n",
    )
    result = checkpoint_book(logger, str(booked), "docs/features/acme")

    assert not result.checkpoint_clean, result.doctor_output
    assert "undeclared-obligation" in result.doctor_output
    assert result.fixup_items
