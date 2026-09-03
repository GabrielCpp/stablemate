"""The convergence gate's scoping and its severity blindness (`shared/checkpoint.py`).

`test_workflow.py` drives the gate end to end and asserts what the loop *does* with a dirty
book. What is asserted here is what the gate counts as dirty in the first place, because that
is the question the whole backfill turns on: the codes deciding whether a book's claims can
ever be observed — `undeclared-obligation`, `compound-normative-bullet`, `weak-check`,
`unstated-precondition` — are all warns, so an error-only gate converges happily on a book in
which nothing is falsifiable.

`scoped_findings` is exercised against literal report dicts rather than through `doctor`.
The filter is about severity and the path prefix, and doctor is not the
thing under test — a fixture book able to produce every combination on demand would be a
larger fiction than the three-key dicts it would be standing in for.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_builder.shared.checkpoint import (
    MAX_FINDINGS_PER_ITEM,
    _repair_items,
    checkpoint_book,
    scoped_findings,
)

BOOK = "docs/features/acme"


def _report(*findings: dict) -> dict:
    return {"findings": list(findings)}


def _finding(code: str, severity: str = "warn", *, path: str = f"{BOOK}/a.md") -> dict:
    return {"severity": severity, "code": code, "path": path,
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


def test_one_item_per_node_and_code() -> None:
    """The split that makes a per-remedy prompt possible.

    Two codes over two nodes of one file is four items, each carrying one code — because the
    prompt for an item is chosen from its kind before the turn starts, and no fragment can be
    written for an item that mixes a dangling link with an unfalsifiable check.

    The refs are doctor's real shape, `<path>#<node>#<member>` — a node id is itself prefixed
    by the file it lives in. Reading the node as everything before the first `#` yields the
    *path*, which puts a whole document back into one item and quietly undoes this split.
    """
    doc = f"{BOOK}/pay.md"
    findings = [
        {**_finding("undeclared-obligation", path=doc), "ref": f"{doc}#charge#returns", "line": 3},
        {**_finding("compound-normative-bullet", path=doc), "ref": f"{doc}#charge#does", "line": 4},
        {**_finding("undeclared-obligation", path=doc), "ref": f"{doc}#refund#returns", "line": 9},
        {**_finding("compound-normative-bullet", path=doc), "ref": f"{doc}#refund#does", "line": 10},
    ]
    items = _repair_items(findings)

    assert sorted(i["kind"] for i in items) == [
        "fix:compound-normative-bullet", "fix:compound-normative-bullet",
        "fix:undeclared-obligation", "fix:undeclared-obligation",
    ]
    # The round is NOT in the target. A survivor is re-queued by `requeue`, which reopens the
    # row `record` already holds; minting `r3:<path>#<node>#<code>` re-queued it as a brand-new
    # row instead, one per finding per round, which is how the loop ran forever.
    assert all(i["target"].startswith(doc) for i in items)
    assert all(i["requeue"] is True for i in items)
    for item in items:
        ctx = json.loads(item["context"])
        assert {f["code"] for f in ctx["findings"]} == {ctx["code"]}
        assert item["kind"] == f"fix:{ctx['code']}"
        assert ctx["node"] in (f"{doc}#charge", f"{doc}#refund")


def test_the_item_order_is_the_drain_order() -> None:
    """Errors first, then grounding → claim shape → obligations → UI, then the rest.

    `select_item` hands out the first pending item, so this sort decides where a bounded
    run's allowance goes. On a drifted book with thousands of findings, a run that stops
    early must have spent itself on the dead citations — a claim about a symbol that no
    longer exists is not worth rephrasing, and a check bound to it observes nothing —
    not on whichever code happens to sort first alphabetically.
    """
    doc = f"{BOOK}/pay.md"
    def at(code: str, node: str, severity: str = "warn") -> dict:
        return {**_finding(code, severity, path=doc), "ref": f"{doc}#{node}#member"}

    findings = [
        at("missing-placement", "hero"),               # UI family
        at("undeclared-obligation", "charge"),          # obligations
        at("aaa-unclassified", "charge"),               # no family: last despite the alphabet
        at("compound-normative-bullet", "charge"),      # claim shape
        at("missing-code-symbol", "refund", "error"),  # error: first regardless of family
        at("dangling-link", "refund"),                  # grounding: first among the warns
    ]
    assert [i["kind"] for i in _repair_items(findings)] == [
        "fix:missing-code-symbol",
        "fix:dangling-link",
        "fix:compound-normative-bullet",
        "fix:undeclared-obligation",
        "fix:missing-placement",
        "fix:aaa-unclassified",
    ]


def test_a_group_finding_is_one_item_scoped_to_every_competitor() -> None:
    """The item a `competing-implementations` turn can actually repair.

    Doctor's finding is already group-scoped, but its `path` names the lowest-sorting member
    and its `ref` is a *source* citation, so this used to fall through `_node_of` to one
    document — while the remedy (point every competitor at one concept) spans all of them.
    The repair prompt's "one node" guardrail then correctly refused the other files and the
    turn reported `skipped`, forever.

    So the identity is the citation and the scope is `related`: one item per competition,
    naming every location it covers and every file they live in.
    """
    a, b = f"{BOOK}/v1.md", f"{BOOK}/v2.md"
    citation = "acme/notify.go::Notify"
    members = [f"{a}#v1", f"{b}#v2"]
    (item,) = _repair_items([{**_finding("competing-implementations", path=a),
                              "ref": citation, "related": members}])

    ctx = json.loads(item["context"])
    assert item["target"] == f"{citation}#competing-implementations"
    assert ctx["citation"] == citation
    assert ctx["related"] == members
    assert ctx["paths"] == [a, b]
    # Neither `path` nor `node` is carried: either would name one arbitrary member as *the*
    # place to open, which is the read the guardrail then honoured.
    assert "path" not in ctx and "node" not in ctx


def test_two_competitions_sharing_a_document_stay_two_items() -> None:
    """Keying on the member made the batching wrong in the other direction too.

    Two unrelated competitions whose lowest-sorting member is the same file were one item —
    up to eight of them on the real book — so `attempts` counted a target that meant nothing
    and one turn was asked for two unrelated concepts.
    """
    a = f"{BOOK}/v1.md"
    items = _repair_items([
        {**_finding("competing-implementations", path=a), "ref": "acme/notify.go::Notify",
         "related": [f"{a}#v1", f"{BOOK}/v2.md#v2"]},
        {**_finding("competing-implementations", path=a), "ref": "acme/pay.go::Charge",
         "related": [f"{a}#v1-charge", f"{BOOK}/v3.md#v3"]},
    ])

    assert len({i["target"] for i in items}) == 2


def test_a_ref_that_is_not_a_node_groups_by_the_file() -> None:
    """Not every finding names a book node, and neither shape may lose one.

    `missing-code-symbol` refs a *source* symbol, and a few checks carry no ref at all. Both
    fall back to the document, which is the only place a repair turn could open anyway.
    """
    doc = f"{BOOK}/pay.md"
    symbol = {**_finding("missing-code-symbol", path=doc), "ref": "acme/service.py::refund"}
    refless = {**_finding("missing-code-symbol", path=doc), "ref": ""}
    (item,) = _repair_items([symbol, refless])

    ctx = json.loads(item["context"])
    assert ctx["node"] == doc
    assert len(ctx["findings"]) == 2


def test_a_grounded_code_is_a_flag_not_a_kind() -> None:
    """`GROUNDED_CODES` stopped naming the item and started describing it.

    The kind has to be the code (the prompt dispatches on it), so "this value must be read out
    of source rather than off the finding" moves into the context where the repair prompt
    branches on it.
    """
    (grounded,) = _repair_items([_finding("missing-placement", path=f"{BOOK}/s.md")])
    (mechanical,) = _repair_items([_finding("undeclared-obligation", path=f"{BOOK}/s.md")])

    assert grounded["kind"] == "fix:missing-placement"
    assert json.loads(grounded["context"])["grounded"] is True
    assert json.loads(mechanical["context"])["grounded"] is False


def test_a_node_past_the_chunk_cap_splits_into_distinct_items() -> None:
    """A node with more findings of one code than a turn should carry is still every finding.

    Silent truncation is the failure the whole gate is built against, so the overflow becomes a
    second worklist entry rather than a dropped tail — and the two targets must differ, or
    `record`'s dedupe by `(kind, target)` collapses them back into one.
    """
    many = [{**_finding("compound-normative-bullet"), "ref": f"{BOOK}/a.md#charge#does", "line": n}
            for n in range(MAX_FINDINGS_PER_ITEM + 1)]
    items = _repair_items(many)

    assert len({i["target"] for i in items}) == 2
    assert sum(len(json.loads(i["context"])["findings"]) for i in items) == len(many)


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
