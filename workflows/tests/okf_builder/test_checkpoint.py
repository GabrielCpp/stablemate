"""The convergence gate's scoping and its severity blindness (`shared/checkpoint.py`)."""
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
    """The gate's whole widening in one assertion."""
    report = _report(_finding("undeclared-obligation"))
    assert [f["code"] for f in scoped_findings(report, "/repo", "")] == [
        "undeclared-obligation"]


def test_findings_outside_the_book_are_not_this_run_s_problem(tmp_path: Path) -> None:
    """A monorepo's unrelated books cannot be repaired by a run scoped to one of them."""
    (tmp_path / BOOK).mkdir(parents=True)
    report = _report(
        _finding("undeclared-obligation", path=f"{BOOK}/mine.md"),
        _finding("undeclared-obligation", path="docs/features/globex/theirs.md"),
        _finding("undeclared-obligation", path="docs/features/acme-legacy/theirs.md"),
    )
    kept = scoped_findings(report, str(tmp_path), str(tmp_path / BOOK))
    assert [f["path"] for f in kept] == [f"{BOOK}/mine.md"]


def test_one_item_per_node_and_code() -> None:
    """The split that makes a per-remedy prompt possible."""
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
    assert all(i["target"].startswith(doc) for i in items)
    assert all(i["requeue"] is True for i in items)
    for item in items:
        ctx = json.loads(item["context"])
        assert {f["code"] for f in ctx["findings"]} == {ctx["code"]}
        assert item["kind"] == f"fix:{ctx['code']}"
        assert ctx["node"] in (f"{doc}#charge", f"{doc}#refund")


def test_the_item_order_is_the_drain_order() -> None:
    """Errors first, then grounding → claim shape → obligations → UI, then the rest."""
    doc = f"{BOOK}/pay.md"
    def at(code: str, node: str, severity: str = "warn") -> dict:
        return {**_finding(code, severity, path=doc), "ref": f"{doc}#{node}#member"}

    findings = [
        at("missing-placement", "hero"),
        at("undeclared-obligation", "charge"),
        at("aaa-unclassified", "charge"),
        at("compound-normative-bullet", "charge"),
        at("missing-code-symbol", "refund", "error"),
        at("dangling-link", "refund"),
    ]
    assert [i["kind"] for i in _repair_items(findings)] == [
        "fix:missing-code-symbol",
        "fix:dangling-link",
        "fix:compound-normative-bullet",
        "fix:undeclared-obligation",
        "fix:missing-placement",
        "fix:aaa-unclassified",
    ]


def test_a_group_finding_is_one_item_scoped_to_every_member() -> None:
    """The item a group-scoped turn can actually repair."""
    a, b = f"{BOOK}/v1.md", f"{BOOK}/v2.md"
    citation = f"{a}#v1:consistency"
    members = [f"{a}#v1", f"{b}#v2"]
    (item,) = _repair_items([{**_finding("same-as-disagreement", path=a),
                              "ref": citation, "related": members}])

    ctx = json.loads(item["context"])
    assert item["target"] == f"{citation}#same-as-disagreement"
    assert ctx["citation"] == citation
    assert ctx["related"] == members
    assert ctx["paths"] == [a, b]
    assert "path" not in ctx and "node" not in ctx


def test_two_group_defects_sharing_a_document_stay_two_items() -> None:
    """Keying on the member made the batching wrong in the other direction too."""
    a = f"{BOOK}/v1.md"
    items = _repair_items([
        {**_finding("same-as-disagreement", path=a), "ref": f"{a}#v1:consistency",
         "related": [f"{a}#v1", f"{BOOK}/v2.md#v2"]},
        {**_finding("same-as-disagreement", path=a), "ref": f"{a}#v1-charge:idempotency",
         "related": [f"{a}#v1-charge", f"{BOOK}/v3.md#v3"]},
    ])

    assert len({i["target"] for i in items}) == 2


def test_a_ref_that_is_not_a_node_groups_by_the_file() -> None:
    """Not every finding names a book node, and neither shape may lose one."""
    doc = f"{BOOK}/pay.md"
    symbol = {**_finding("missing-code-symbol", path=doc), "ref": "acme/service.py::refund"}
    refless = {**_finding("missing-code-symbol", path=doc), "ref": ""}
    (item,) = _repair_items([symbol, refless])

    ctx = json.loads(item["context"])
    assert ctx["node"] == doc
    assert len(ctx["findings"]) == 2


def test_an_indexed_file_node_ref_mints_one_item_per_bullet() -> None:
    """The row split doctor's per-bullet index causes on a *file* node, on the record."""
    doc = f"{BOOK}/pay.md"
    items = _repair_items([
        {**_finding("unparsed-check", path=doc), "ref": f"{doc}#verify:1"},
        {**_finding("unparsed-check", path=doc), "ref": f"{doc}#verify:2"},
    ])

    assert [i["target"] for i in items] == [
        f"{doc}#{doc}#verify:1#unparsed-check", f"{doc}#{doc}#verify:2#unparsed-check"]


def test_a_grounded_code_is_a_flag_not_a_kind() -> None:
    """`GROUNDED_CODES` stopped naming the item and started describing it."""
    (grounded,) = _repair_items([_finding("missing-placement", path=f"{BOOK}/s.md")])
    (mechanical,) = _repair_items([_finding("undeclared-obligation", path=f"{BOOK}/s.md")])

    assert grounded["kind"] == "fix:missing-placement"
    assert json.loads(grounded["context"])["grounded"] is True
    assert json.loads(mechanical["context"])["grounded"] is False


def test_a_node_past_the_chunk_cap_splits_into_distinct_items() -> None:
    """A node with more findings of one code than a turn should carry is still every finding."""
    many = [{**_finding("compound-normative-bullet"), "ref": f"{BOOK}/a.md#charge#does", "line": n}
            for n in range(MAX_FINDINGS_PER_ITEM + 1)]
    items = _repair_items(many)

    assert len({i["target"] for i in items}) == 2
    assert sum(len(json.loads(i["context"])["findings"]) for i in items) == len(many)


def test_a_book_with_warnings_and_no_errors_is_dirty(
    booked: Path, write: Callable[[Path, str], Path], logger: logging.Logger
) -> None:
    """The gate, end to end, on the case the error-only version called finished."""
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


def test_an_open_repair_whose_finding_stopped_firing_is_closed_at_the_checkpoint(tmp_path: Path) -> None:
    from workhorse_workflows.okf_builder.shared.worklist import record

    doctor = json.dumps({"findings": [{"code": "x"}]})
    worklist = tmp_path / "w.json"
    rows = [
        {"kind": "fix:undeclared-obligation", "target": "a.md#a.md#field-x#undeclared-obligation",
         "status": "pending", "context": doctor, "attempts": 0},
        {"kind": "fix:undeclared-obligation", "target": "a.md#a.md#publish#undeclared-obligation",
         "status": "pending", "context": doctor, "attempts": 0},
        {"kind": "fix:weak-check", "target": "a.md#a.md#publish#weak-check",
         "status": "blocked", "blocked_reason": "code fix", "context": doctor, "attempts": 3},
        {"kind": "fix:stale-citation", "target": "a.md#a.md#publish#stale-citation",
         "status": "blocked", "blocked_reason": "moved", "context": "{}", "attempts": 3},
        {"kind": "change", "target": "docs/features/acme/a.md", "status": "pending", "context": ""},
    ]
    worklist.write_text(json.dumps({"items": rows}))
    standing = [{"kind": "fix:undeclared-obligation",
                 "target": "a.md#a.md#publish#undeclared-obligation", "context": "", "requeue": True}]
    plain = record(logging.getLogger("t"), str(worklist), None, standing)
    assert plain.settled == 0 and plain.pending_count == 3
    settled = record(logging.getLogger("t"), str(worklist), None, standing, settle_fix_items=True)
    assert settled.settled == 2 and settled.pending_count == 2 and settled.blocked_count == 1
    by_target = {i["target"]: i for i in json.loads(worklist.read_text())["items"]}
    field = by_target["a.md#a.md#field-x#undeclared-obligation"]
    assert field["status"] == "done" and field["doc_status"] == "stale"
    assert by_target["a.md#a.md#publish#undeclared-obligation"]["status"] == "pending"
    assert by_target["a.md#a.md#publish#weak-check"]["status"] == "done"
    assert by_target["a.md#a.md#publish#stale-citation"]["status"] == "blocked"
    assert by_target["docs/features/acme/a.md"]["status"] == "pending"


def _standing_repair(repo: Path) -> dict:
    """The one repair item `checkpoint_book` would queue on `dirty`, keyed as it keys it."""
    from ostler import Ostler

    items = _repair_items(scoped_findings(Ostler(str(repo)).doctor().data, str(repo), BOOK))
    assert len(items) == 1, items
    return items[0]


def _stale_worklist(path: Path, standing: dict, *, settled_done: int | None = None) -> Path:
    """Two pending repairs, one of which doctor still reports."""
    data: dict = {
        "items": [
            {"kind": standing["kind"], "target": standing["target"],
             "status": "pending", "context": standing["context"], "attempts": 0},
            {"kind": "fix:undeclared-obligation",
             "target": f"{BOOK}/concepts/charge.md#charge#undeclared-obligation",
             "status": "pending", "context": json.dumps({"findings": []}), "attempts": 0},
            {"kind": "change", "target": f"{BOOK}/concepts/charge.md", "status": "pending",
             "context": ""},
            *({"kind": "surface", "target": f"s{n}", "status": "done", "context": ""}
              for n in range(30)),
        ],
    }
    if settled_done is not None:
        data["settled_done"] = settled_done
    path.write_text(json.dumps(data))
    return path


def test_the_drain_settles_a_stale_repair_before_it_is_picked(
    dirty: Path, tmp_path: Path, logger: logging.Logger
) -> None:
    """A pending `fix:` row doctor no longer names is closed mid-drain, not at the checkpoint."""
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    worklist = _stale_worklist(tmp_path / "w.json", standing)
    result = settle_stale(logger, str(worklist), str(dirty), BOOK)

    assert result.ran and result.settled == 1 and result.standing == 1 and not result.error
    assert result.pending_count == 2 and result.at_done == 31
    data = json.loads(worklist.read_text())
    assert data["settled_done"] == 31
    by_target = {i["target"]: i for i in data["items"]}
    stale = by_target[f"{BOOK}/concepts/charge.md#charge#undeclared-obligation"]
    assert stale["status"] == "done" and stale["doc_status"] == "stale"
    assert "mid-drain" in stale["note"]
    assert by_target[standing["target"]]["status"] == "pending"
    assert by_target[f"{BOOK}/concepts/charge.md"]["status"] == "pending"


def test_the_settle_is_amortized_over_the_drain(
    dirty: Path, tmp_path: Path, logger: logging.Logger
) -> None:
    """Doctor is read on first entry and then once per `every` completed items, not per pick."""
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    recent = _stale_worklist(tmp_path / "recent.json", standing, settled_done=10)
    skipped = settle_stale(logger, str(recent), str(dirty), BOOK, every=25)
    assert not skipped.ran and skipped.settled == 0
    assert json.loads(recent.read_text())["settled_done"] == 10

    due = _stale_worklist(tmp_path / "due.json", standing, settled_done=5)
    ran = settle_stale(logger, str(due), str(dirty), BOOK, every=25)
    assert ran.ran and ran.settled == 1 and json.loads(due.read_text())["settled_done"] == 31


def test_a_settle_with_nothing_to_settle_does_not_read_doctor(
    tmp_path: Path, logger: logging.Logger
) -> None:
    """No pending repair rows: no doctor pass, no write — `repo_root` need not even exist."""
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    worklist = tmp_path / "w.json"
    worklist.write_text(json.dumps({"items": [
        {"kind": "change", "target": "a.md", "status": "pending", "context": ""},
        {"kind": "fix:weak-check", "target": "a.md#a#weak-check", "status": "blocked",
         "context": "", "attempts": 3},
    ]}))
    result = settle_stale(logger, str(worklist), str(tmp_path / "nowhere"), BOOK)
    assert not result.ran and result.pending_count == 1
    assert "settled_done" not in json.loads(worklist.read_text())


def test_a_watermark_above_the_done_count_is_stale(
    dirty: Path, tmp_path: Path, logger: logging.Logger
) -> None:
    """Checkpoint requeues move done rows back to pending, so the done count falls."""
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    worklist = _stale_worklist(tmp_path / "w.json", standing, settled_done=100)
    result = settle_stale(logger, str(worklist), str(dirty), BOOK, every=25)
    assert result.ran and result.settled == 1
    assert json.loads(worklist.read_text())["settled_done"] == 31


def test_reopening_a_stale_closure_is_not_a_failed_repair(tmp_path: Path) -> None:
    """A row the settle closed `stale` never had a repair turn, so its requeue costs no attempt."""
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist = tmp_path / "w.json"
    target = "a.md#a.md#publish#undeclared-obligation"
    worklist.write_text(json.dumps({"items": [
        {"kind": "fix:undeclared-obligation", "target": target, "status": "done",
         "doc_status": "stale", "note": "doctor no longer reports this finding; closed mid-drain",
         "context": "", "attempts": 2},
    ]}))
    standing = [{"kind": "fix:undeclared-obligation", "target": target,
                 "context": "{}", "requeue": True}]
    result = record(logging.getLogger("t"), str(worklist), None, standing, max_attempts=3)
    assert result.pending_count == 1 and result.blocked_count == 0
    row = json.loads(worklist.read_text())["items"][0]
    assert row["status"] == "pending" and row["attempts"] == 2
    assert "doc_status" not in row and "note" not in row and "blocked_reason" not in row

    worklist.write_text(json.dumps({"items": [
        {"kind": "fix:undeclared-obligation", "target": target, "status": "done",
         "doc_status": "stale", "note": "doctor no longer reports this finding; closed mid-drain",
         "blocked_reason": "the source has no verify seam", "context": "", "attempts": 3},
    ]}))
    reblocked = record(logging.getLogger("t"), str(worklist), None, standing, max_attempts=3)
    assert reblocked.blocked_count == 1
    row = json.loads(worklist.read_text())["items"][0]
    assert row["status"] == "blocked" and row["blocked_reason"] == "the source has no verify seam"


def _repair_row_fixture(tmp_path: Path) -> tuple[Path, Path, dict, list[dict]]:
    doc = tmp_path / "docs/features/a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\ntype: api\nslug: a\ntitle: A\n---\n# A\n\n## Endpoints\n\n"
                   "### publish\n- route: `POST /p`\n\n### list\n- route: `GET /p`\n")
    context = json.dumps({"code": "undeclared-obligation", "path": "docs/features/a.md",
                          "node": "docs/features/a.md#publish"})
    target = "docs/features/a.md#docs/features/a.md#publish#undeclared-obligation"
    row = {"kind": "fix:undeclared-obligation", "target": target, "context": context}
    worklist = tmp_path / "w.json"
    worklist.write_text(json.dumps({"items": [{**row, "status": "pending", "attempts": 0}]}))
    return worklist, doc, row, [{**row, "requeue": True}]


def test_a_finding_standing_over_the_node_the_turn_left_costs_an_attempt(tmp_path: Path) -> None:
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist, doc, row, standing = _repair_row_fixture(tmp_path)
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented", repo_root=str(tmp_path))
    doc.write_text(doc.read_text().replace("GET /p", "GET /q"))
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 1


def test_a_finding_standing_over_a_node_rewritten_since_the_close_is_free(tmp_path: Path) -> None:
    """The verdict was about text that no longer exists, so it is not a failed repair."""
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist, doc, row, standing = _repair_row_fixture(tmp_path)
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented", note="bound a verify",
           repo_root=str(tmp_path))
    doc.write_text(doc.read_text().replace("POST /p", "POST /r"))
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 0
    assert "doc_status" not in item and "note" not in item and "closed_digest" not in item

    record(log, str(worklist), row, None, doc_status="documented", repo_root=str(tmp_path))
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    assert json.loads(worklist.read_text())["items"][0]["attempts"] == 1


def test_a_close_with_no_digest_is_counted_as_before(tmp_path: Path) -> None:
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist, doc, row, standing = _repair_row_fixture(tmp_path)
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented")
    doc.write_text(doc.read_text().replace("POST /p", "POST /r"))
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    assert json.loads(worklist.read_text())["items"][0]["attempts"] == 1


def _behavior_repair_row_fixture(tmp_path: Path) -> tuple[Path, Path, dict, list[dict]]:
    doc = tmp_path / "docs/features/a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# A\n\nOriginal claim.\n")
    target = "docs/features/a.md"
    row = {"kind": "behavior-repair", "target": target,
           "context": "partial: the claim does not name the retry cap"}
    worklist = tmp_path / "w.json"
    worklist.write_text(json.dumps({"items": [{**row, "status": "pending", "attempts": 0}]}))
    return worklist, doc, row, [{**row, "requeue": True}]


def test_a_behavior_repair_standing_over_a_target_rewritten_since_the_close_is_free(
    tmp_path: Path,
) -> None:
    """A `behavior-repair` row's context is the auditor's prose, not a `{node, path}` scope, so the free reopen a `fix:` row gets when its node changes under it used to be unreachable for these rows — every reopen was counted, even one over a target the previous turn had genuinely rewritten, and a repair that landed still walked the row to `blocked`."""
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist, doc, row, standing = _behavior_repair_row_fixture(tmp_path)
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented", repo_root=str(tmp_path))
    doc.write_text(doc.read_text() + "\nThe retry cap is three attempts.\n")
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 0


def test_a_behavior_repair_settled_by_a_coverage_waiver_is_free(tmp_path: Path) -> None:
    """An undocumented-file `behavior-repair` is legitimately settled by a `coverage-waivers.json` entry for its `target`, not by an edit to the target itself — so the digest that decides whether a reopen is free has to see the waivers file too, when `features_root` is given."""
    from workhorse_workflows.okf_builder.shared import paths
    from workhorse_workflows.okf_builder.shared.worklist import record

    features = tmp_path / "docs/features/a"
    features.mkdir(parents=True)
    src = tmp_path / "a/mock.go"
    src.parent.mkdir(parents=True)
    src.write_text("package a\n")
    target = "a/mock.go"
    row = {"kind": "behavior-repair", "target": target,
           "context": "Undocumented file a/mock.go: no claim in the book cites this file."}
    worklist = tmp_path / "w.json"
    worklist.write_text(json.dumps({"items": [{**row, "status": "pending", "attempts": 0}]}))
    standing = [{**row, "requeue": True}]
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented",
           repo_root=str(tmp_path), features_root=str(features))
    paths.waivers_path(str(features)).write_text(
        json.dumps([{"code": target, "reason": "test double"}])
    )
    record(log, str(worklist), None, standing,
           repo_root=str(tmp_path), features_root=str(features))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 0


def test_the_drain_reopens_a_done_repair_whose_finding_still_stands(
    dirty: Path, tmp_path: Path, logger: logging.Logger
) -> None:
    """The settle's doctor read reopens a standing done row now, not when the drain goes dry."""
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    worklist = _stale_worklist(tmp_path / "w.json", standing)
    data = json.loads(worklist.read_text())
    data["items"][0].update(status="done", doc_status="documented", note="turn said so")
    worklist.write_text(json.dumps(data))

    result = settle_stale(logger, str(worklist), str(dirty), BOOK)

    assert result.ran and result.reopened == 1 and result.settled == 1
    row = {i["target"]: i for i in json.loads(worklist.read_text())["items"]}[standing["target"]]
    assert row["status"] == "pending" and row["attempts"] == 1


def test_a_done_repair_standing_only_on_fixable_findings_is_left_to_the_checkpoint(
    tmp_path: Path, logger: logging.Logger, monkeypatch
) -> None:
    """The checkpoint's autofix clears a `fixable` finding before its doctor read; the settle must not rewrite the book, so reopening that row mid-drain would buy a turn for nothing."""
    from workhorse_workflows.okf_builder.shared import checkpoint

    fixable = {**_finding("dangling-link"), "fixable": True}
    shaped = _finding("compound-normative-bullet", path=f"{BOOK}/b.md")
    items = _repair_items([fixable, shaped])

    class _Doctor:
        data: dict = {}

    class _Ostler:
        def __init__(self, _root: str) -> None: ...

        def doctor(self) -> _Doctor:
            return _Doctor()

    monkeypatch.setattr(checkpoint, "Ostler", _Ostler)
    monkeypatch.setattr(checkpoint, "scoped_findings", lambda *_a: [fixable, shaped])
    worklist = tmp_path / "w.json"
    worklist.write_text(json.dumps({"items": [
        {"kind": i["kind"], "target": i["target"], "status": "done", "context": i["context"],
         "attempts": 0} for i in items
    ]}))

    result = checkpoint.settle_stale(logger, str(worklist), str(tmp_path), BOOK)

    assert result.reopened == 1
    status = {i["kind"]: i["status"] for i in json.loads(worklist.read_text())["items"]}
    assert status == {"fix:dangling-link": "done", "fix:compound-normative-bullet": "pending"}


def test_a_page_documenting_a_test_double_is_one_deletion_row() -> None:
    """Everything on a `test-subject` page is undone by deleting it, so only the verdict queues."""
    mock = f"{BOOK}/mock-billing.md"
    product = f"{BOOK}/billing.md"
    findings = [
        {**_finding("test-subject", "error", path=mock), "ref": f"{mock}#code"},
        {**_finding("test-subject", "error", path=mock), "ref": f"{mock}#method-charge#code"},
        {**_finding("undeclared-obligation", path=mock), "ref": f"{mock}#method-charge#does"},
        {**_finding("missing-code-symbol", "error", path=mock), "ref": f"{mock}#code"},
        {**_finding("undeclared-obligation", path=product), "ref": f"{product}#charge#does"},
    ]

    assert sorted(i["target"] for i in _repair_items(findings)) == [
        f"{product}#{product}#charge#undeclared-obligation",
        f"{mock}#{mock}#code#test-subject",
    ]


def test_a_test_double_node_on_a_product_page_drops_only_its_own_findings() -> None:
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("test-subject", "error", path=doc), "ref": f"{doc}#fake-stripe#code"},
        {**_finding("weak-check", path=doc), "ref": f"{doc}#fake-stripe#verify"},
        {**_finding("weak-check", path=doc), "ref": f"{doc}#charge#verify"},
    ]

    assert sorted(i["kind"] for i in _repair_items(findings)) == [
        "fix:test-subject", "fix:weak-check"]
    (weak,) = [i for i in _repair_items(findings) if i["kind"] == "fix:weak-check"]
    assert "#charge#" in weak["target"]


def test_test_subjects_drain_before_everything_else() -> None:
    """Deleting a mock page first spares the turns every other row would spend on it."""
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("missing-code-symbol", "error", path=doc), "ref": f"{doc}#charge#code"},
        {**_finding("code-cites-test", "error", path=doc), "ref": f"{doc}#refund#code"},
    ]

    assert _repair_items(findings)[0]["kind"] == "fix:code-cites-test"


def test_unstamped_and_unreachable_citations_queue_no_repair_row() -> None:
    """Neither code is an agent's to fix — ostler itself clears both, so nothing is queued."""
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("unstamped-citation", path=doc), "ref": f"{doc}#charge#code"},
        {**_finding("unreachable-citation", path=doc), "ref": f"{doc}#refund#code"},
    ]

    assert _repair_items(findings) == []


def test_an_unwitnessed_check_queues_no_repair_row_but_a_sibling_finding_still_does() -> None:
    """`unwitnessed-check` reports the sensitivity harness's reach, not a book defect."""
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("unwitnessed-check", path=doc), "ref": f"{doc}#charge#code"},
        {**_finding("missing-code-symbol", severity="error", path=doc), "ref": f"{doc}#charge#code"},
    ]

    items = _repair_items(findings)

    assert len(items) == 1
    assert items[0]["kind"] == "fix:missing-code-symbol"


def _stub_ostler(monkeypatch, findings: list[dict]) -> None:
    """Point `checkpoint_book` at a fake `Ostler`/`scoped_findings` instead of a real book."""
    from workhorse_workflows.okf_builder.shared import checkpoint

    class _Doctor:
        data: dict = {}

    class _Ostler:
        def __init__(self, _root: str) -> None: ...

        def doctor(self) -> _Doctor:
            return _Doctor()

    monkeypatch.setattr(checkpoint, "Ostler", _Ostler)
    monkeypatch.setattr(checkpoint, "scoped_findings", lambda *_a: findings)


def test_a_book_standing_only_on_non_actionable_and_regrounding_codes_is_clean(
    logger: logging.Logger, monkeypatch,
) -> None:
    """The gate agrees with the queue: nothing here is a turn's to fix, so nothing is queued."""
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("unstamped-citation", path=doc), "ref": f"{doc}#charge#code"},
        {**_finding("unreachable-citation", path=doc), "ref": f"{doc}#refund#code"},
        {**_finding("stale-citation", severity="error", path=doc), "ref": f"{doc}#refund#code"},
    ]
    _stub_ostler(monkeypatch, findings)

    result = checkpoint_book(logger, ".", "")

    assert result.checkpoint_clean, result.doctor_output
    assert result.fixup_items == []


def test_a_finding_beside_them_keeps_the_book_dirty(
    logger: logging.Logger, monkeypatch,
) -> None:
    """One actionable finding alongside the excused codes is enough to reopen the gate."""
    doc = f"{BOOK}/billing.md"
    findings = [
        {**_finding("unstamped-citation", path=doc), "ref": f"{doc}#charge#code"},
        {**_finding("unreachable-citation", path=doc), "ref": f"{doc}#refund#code"},
        {**_finding("stale-citation", severity="error", path=doc), "ref": f"{doc}#refund#code"},
        {**_finding("missing-code-symbol", severity="error", path=doc), "ref": f"{doc}#refund#code"},
    ]
    _stub_ostler(monkeypatch, findings)

    result = checkpoint_book(logger, ".", "")

    assert not result.checkpoint_clean, result.doctor_output
    assert result.fixup_items
