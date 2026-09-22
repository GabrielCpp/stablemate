"""The compiler's gaps reaching the repair loop (`shared/gaps.py`)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

import pytest
from ostler import Ostler
from ostler.qa.compile import Gap
from workhorse_workflows.okf_builder.shared import checkpoint, gaps

BOOK = "docs/features/acme"
PAGE = f"{BOOK}/billing.md"
NODE = f"{PAGE}#charge"
OBLIGATION = f"okf:{NODE}:contract"


@dataclass
class _Result:
    gaps: list[Gap]


def _context(**overrides: object) -> dict:
    obligation = {
        "id": OBLIGATION, "node": NODE, "source": PAGE, "docPosition": [4, 9],
        **overrides,
    }
    return {"obligations": [obligation]}


def _stub_compiler(monkeypatch, context: dict, *gap_list: Gap) -> None:
    """Point `compile_gap_findings` at a fixed context and gap report."""
    monkeypatch.setattr(gaps, "book_context", lambda *_a, **_k: context)
    monkeypatch.setattr(gaps, "compile_plan_gaps", lambda *_a, **_k: _Result(list(gap_list)))


def test_a_gap_is_located_on_the_node_that_owes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gap names an obligation; the repair loop groups by page and node, so it needs both."""
    _stub_compiler(monkeypatch, _context(), Gap(OBLIGATION, "unarranged-scenario", "no arrangement"))

    row, = gaps.compile_gap_findings("/repo", f"/repo/{BOOK}")

    assert row["path"] == PAGE
    assert row["ref"] == NODE
    assert row["line"] == 9
    assert row["code"] == "unarranged-scenario"
    assert row["severity"] == "error"


def test_a_warning_gap_keeps_its_severity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A claim that declares no check is a warn, and a warn is still work somebody does."""
    _stub_compiler(monkeypatch, _context(), Gap(OBLIGATION, "no-verify-declared", "no verify"))

    row, = gaps.compile_gap_findings("/repo", f"/repo/{BOOK}")

    assert (row["severity"], row["code"]) == ("warn", "undeclared-obligation")


def test_a_warning_gap_still_queues_a_repair_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """Left standing, that warning is the check the operator writes later instead."""
    _stub_compiler(monkeypatch, _context(), Gap(OBLIGATION, "no-verify-declared", "no verify"))

    items = checkpoint._repair_items(gaps.compile_gap_findings("/repo", f"/repo/{BOOK}"))

    assert [item["kind"] for item in items] == ["fix:undeclared-obligation"]


def test_a_gap_whose_obligation_is_unknown_falls_back_to_its_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row with no page groups under the empty path, where no repair prompt can read it."""
    _stub_compiler(monkeypatch, {"obligations": []}, Gap(NODE, "unarranged-state", "no state"))

    row, = gaps.compile_gap_findings("/repo", f"/repo/{BOOK}")

    assert row["path"] == PAGE
    assert row["ref"] == NODE


def test_the_seeder_reads_both_checkers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doctor sees the graph, the compiler sees the compiled context, the loop seeds from both."""
    monkeypatch.setattr(
        checkpoint, "scoped_findings",
        lambda report, *_a: list(report.get("findings", [])),
    )
    _stub_compiler(monkeypatch, _context(), Gap(OBLIGATION, "unarranged-scenario", "no arrangement"))
    graph_finding = {"severity": "error", "code": "missing-code-symbol", "path": PAGE,
                     "ref": f"{NODE}#code", "line": 1}

    class _Ostler:
        def doctor(self) -> object:
            return type("_Report", (), {"data": {"findings": [graph_finding]}})()

    found = checkpoint.book_findings(
        logging.getLogger("test"), cast(Ostler, _Ostler()), "/repo", f"/repo/{BOOK}",
    )

    assert [f["code"] for f in found] == ["missing-code-symbol", "unarranged-scenario"]


def test_a_compiler_failure_leaves_doctor_s_findings_standing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book too broken to compile is exactly the book whose graph findings must still queue."""
    monkeypatch.setattr(
        checkpoint, "scoped_findings",
        lambda report, *_a: list(report.get("findings", [])),
    )

    def _boom(*_a: object, **_k: object) -> list[dict]:
        raise ValueError("no context")

    monkeypatch.setattr(checkpoint, "compile_gap_findings", _boom)
    graph_finding = {"severity": "error", "code": "missing-code-symbol", "path": PAGE,
                     "ref": f"{NODE}#code", "line": 1}

    class _Ostler:
        def doctor(self) -> object:
            return type("_Report", (), {"data": {"findings": [graph_finding]}})()

    found = checkpoint.book_findings(
        logging.getLogger("test"), cast(Ostler, _Ostler()), "/repo", f"/repo/{BOOK}",
    )

    assert [f["code"] for f in found] == ["missing-code-symbol"]


def _reported(kind: str, obligation: str = OBLIGATION) -> dict:
    """A gap shaped the way a live-audit report carries it."""
    return {"obligation_id": obligation, "kind": kind, "detail": f"no {kind}"}


def test_a_reported_gap_becomes_a_repair_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """The audit already compiled the plan, so its own gap list is the work to queue."""
    monkeypatch.setattr(gaps, "book_context", lambda *_a, **_k: _context())

    items = checkpoint.audit_gap_items(
        logging.getLogger("test"), "/repo", f"/repo/{BOOK}",
        [_reported("unarranged-scenario"), _reported("no-verify-declared")],
    )

    assert [item["kind"] for item in items] == [
        "fix:unarranged-scenario", "fix:undeclared-obligation",
    ]
    assert {item["target"] for item in items} == {
        f"{PAGE}#{NODE}#unarranged-scenario", f"{PAGE}#{NODE}#undeclared-obligation",
    }


def test_a_report_with_no_gaps_queues_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean report must not reopen the book, so the compiler is never called."""
    def _never(*_a: object, **_k: object) -> dict:
        raise AssertionError("the book was read for an empty gap list")

    monkeypatch.setattr(gaps, "book_context", _never)

    assert checkpoint.audit_gap_items(logging.getLogger("test"), "/repo", f"/repo/{BOOK}", []) == []


def test_gaps_that_cannot_be_located_reach_the_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no row to queue, `semantic_audit` gates rather than dropping the gap."""
    def _boom(*_a: object, **_k: object) -> dict:
        raise OSError("no book")

    monkeypatch.setattr(gaps, "book_context", _boom)

    items = checkpoint.audit_gap_items(
        logging.getLogger("test"), "/repo", f"/repo/{BOOK}", [_reported("unarranged-scenario")],
    )

    assert items == []


def test_an_obligation_no_runner_can_stand_in_queues_no_repair_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D1's dispatch table owes a `concept` node no row, so no check it declares is ever run."""
    monkeypatch.setattr(gaps, "book_context", lambda *_a, **_k: _context(nodeType="concept"))

    items = checkpoint.audit_gap_items(
        logging.getLogger("test"), "/repo", f"/repo/{BOOK}",
        [_reported("no-verify-declared")],
    )

    assert items == []


def test_a_gap_on_a_hostable_node_still_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    """An `endpoint` has a row in that table, so the check it lacks is work somebody does."""
    monkeypatch.setattr(gaps, "book_context", lambda *_a, **_k: _context(nodeType="endpoint"))

    items = checkpoint.audit_gap_items(
        logging.getLogger("test"), "/repo", f"/repo/{BOOK}",
        [_reported("no-verify-declared")],
    )

    assert [item["kind"] for item in items] == ["fix:undeclared-obligation"]
