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


def test_an_indexed_file_node_ref_mints_one_item_per_bullet() -> None:
    """The row split doctor's per-bullet index causes on a *file* node, on the record.

    Doctor addresses a per-bullet finding as `<node>#<key>:<index>` so two defects under one
    repeatable key stop sharing an address — without it the drain collapsed them into one row
    with one three-attempt budget and the repair turn answered whichever sibling it read. A
    document's file node has the bare path as its id, so its findings ref `<path>#<key>:<n>`
    and `_node_of` reads that whole segment as the node: one row becomes one row per index.

    That is the intended consequence, not a regression — one row per addressable finding, each
    with its own budget. It costs a one-time churn on any in-flight run (`settle_stale_rows`
    closes the old-shaped rows and opens these at `attempts: 0`) and one restart of the
    whole-book stall comparison, since `_signature` is keyed on `(code, path, ref)`.
    """
    doc = f"{BOOK}/pay.md"
    items = _repair_items([
        {**_finding("unparsed-check", path=doc), "ref": f"{doc}#verify:1"},
        {**_finding("unparsed-check", path=doc), "ref": f"{doc}#verify:2"},
    ])

    assert [i["target"] for i in items] == [
        f"{doc}#{doc}#verify:1#unparsed-check", f"{doc}#{doc}#verify:2#unparsed-check"]


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


def test_an_open_repair_whose_finding_stopped_firing_is_closed_at_the_checkpoint(tmp_path: Path) -> None:
    # A doctor rule retired under the run (field nodes stopped owing `undeclared-obligation`)
    # left hundreds of pending rows nothing would ever re-raise; each was a repair turn spent
    # finding nothing to do. Blocked doctor rows settle by the same rule: a gate parked for
    # hours on findings a concurrent writer had already cleared asked about nothing. A
    # coverage `fix:stale-citation` row is not doctor's to settle, blocked or not.
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
    """A pending `fix:` row doctor no longer names is closed mid-drain, not at the checkpoint.

    `dirty` still owes `missing-code-symbol` on refund.md, so that row stands; nothing
    reports `undeclared-obligation` on charge.md, so that row is the stale one — the turn
    this pass exists to not spend.
    """
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    worklist = _stale_worklist(tmp_path / "w.json", standing)
    result = settle_stale(logger, str(worklist), str(dirty), BOOK)

    assert result.ran and result.settled == 1 and result.standing == 1 and not result.error
    # The one closed row counts as done, and the watermark is taken after the close.
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
    """Checkpoint requeues move done rows back to pending, so the done count falls.

    A watermark taken at a higher count would otherwise hold the settle off until the
    drain re-earned every requeued row plus `every` — hundreds of repair turns on rows
    doctor had already stopped reporting.
    """
    from workhorse_workflows.okf_builder.shared.checkpoint import settle_stale

    standing = _standing_repair(dirty)
    worklist = _stale_worklist(tmp_path / "w.json", standing, settled_done=100)
    result = settle_stale(logger, str(worklist), str(dirty), BOOK, every=25)
    assert result.ran and result.settled == 1
    assert json.loads(worklist.read_text())["settled_done"] == 31


def test_reopening_a_stale_closure_is_not_a_failed_repair(tmp_path: Path) -> None:
    """A row the settle closed `stale` never had a repair turn, so its requeue costs no attempt.

    Counting it spent the budget on flicker, and the block that followed quoted the
    settle's own note — "doctor no longer reports this finding" — as the reason a finding
    doctor *does* report could not be fixed.
    """
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

    # A row blocked on real attempts, then settled, re-blocks on its own reason when the
    # finding comes back — not on the settle's note, and not on "no reason".
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
    # A sibling node changing is not this node changing.
    doc.write_text(doc.read_text().replace("GET /p", "GET /q"))
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 1


def test_a_finding_standing_over_a_node_rewritten_since_the_close_is_free(tmp_path: Path) -> None:
    """The verdict was about text that no longer exists, so it is not a failed repair.

    A run moved to another checkout of the book reopened hundreds of rows its turns had
    closed on the old tree, and counted every one — escalating the model tier and walking
    each row toward a block no turn on the current text had earned.
    """
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

    # The next close seals the new text, and a failure over it counts again.
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
    """A `behavior-repair` row's context is the auditor's prose, not a `{node, path}` scope,
    so the free reopen a `fix:` row gets when its node changes under it used to be
    unreachable for these rows — every reopen was counted, even one over a target the
    previous turn had genuinely rewritten, and a repair that landed still walked the row to
    `blocked`.
    """
    from workhorse_workflows.okf_builder.shared.worklist import record

    worklist, doc, row, standing = _behavior_repair_row_fixture(tmp_path)
    log = logging.getLogger("t")
    record(log, str(worklist), row, None, doc_status="documented", repo_root=str(tmp_path))
    doc.write_text(doc.read_text() + "\nThe retry cap is three attempts.\n")
    record(log, str(worklist), None, standing, repo_root=str(tmp_path))
    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending" and item["attempts"] == 0


def test_a_behavior_repair_settled_by_a_coverage_waiver_is_free(tmp_path: Path) -> None:
    """An undocumented-file `behavior-repair` is legitimately settled by a
    `coverage-waivers.json` entry for its `target`, not by an edit to the target itself —
    so the digest that decides whether a reopen is free has to see the waivers file too,
    when `features_root` is given.
    """
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
    """The settle's doctor read reopens a standing done row now, not when the drain goes dry.

    The row carries no `closed_digest`, so the reopen is a counted attempt — the rule
    `record` applies at the checkpoint, run sooner, so the row batches with the file's
    other pending work instead of costing a second turn on it later.
    """
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
    """The checkpoint's autofix clears a `fixable` finding before its doctor read; the settle
    must not rewrite the book, so reopening that row mid-drain would buy a turn for nothing."""
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
