"""A repair turn takes every open doctor row on its file, and closes all of them.

The checkpoint's row is one `(file, node, code)` — the unit a finding is tracked by across
rounds. The turn is one file, because what a turn costs is reading the file and its source,
and that is paid once however many codes the file carries (`worklist._batch`).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workhorse.templates import render

import workhorse_workflows
from workhorse_workflows.okf_builder.main.flow import repair_power
from workhorse_workflows.okf_builder.shared.worklist import MAX_BATCH_FINDINGS, record, select_item

WORKFLOW_DIR = Path(workhorse_workflows.__file__).parent / "okf_builder"
BOOK = "docs/features/acme"
LOG = logging.getLogger("t")


def _row(code: str, path: str, node: str, *lines: int, status: str = "pending") -> dict:
    return {
        "kind": f"fix:{code}",
        "target": f"{path}#{node}#{code}",
        "status": status,
        "attempts": 0,
        "context": json.dumps({
            "code": code, "node": node, "path": path, "grounded": False,
            "findings": [{"code": code, "line": n, "message": "…"} for n in lines],
        }),
    }


def _group_row(path: str) -> dict:
    return {
        "kind": "fix:competing-implementations",
        "target": "acme/refund.py::refund#competing-implementations",
        "status": "pending",
        "attempts": 0,
        "context": json.dumps({
            "code": "competing-implementations", "citation": "acme/refund.py::refund",
            "related": [f"{path}#refund", f"{BOOK}/b.md#refund"], "paths": [path, f"{BOOK}/b.md"],
            "grounded": False, "findings": [{"code": "competing-implementations", "line": 1}],
        }),
    }


def _worklist(tmp_path: Path, *rows: dict) -> Path:
    path = tmp_path / "acme.worklist.json"
    path.write_text(json.dumps({"items": list(rows)}))
    return path


def _statuses(path: Path) -> list[str]:
    return [row["status"] for row in json.loads(path.read_text())["items"]]


def test_a_repair_takes_every_open_row_on_its_file_and_nothing_else(tmp_path: Path) -> None:
    a = f"{BOOK}/a.md"
    worklist = _worklist(
        tmp_path,
        _row("dangling-link", a, "refund", 30),
        _row("dangling-link", f"{BOOK}/b.md", "refund", 4),
        _row("weak-check", a, "refund", 12),
        _group_row(a),
        _row("stale-citation", a, "refund", 8),
        _row("weak-check", a, "capture", 50),
    )

    pick = select_item(LOG, str(worklist))

    assert pick.current_item["target"] == f"{a}#refund#dangling-link"
    assert [r["target"] for r in pick.batch] == [f"{a}#refund#weak-check", f"{a}#capture#weak-check"]
    assert pick.item_codes == ["dangling-link", "weak-check"]
    assert _statuses(worklist) == ["active", "pending", "active", "pending", "pending", "active"]
    context = json.loads(pick.item_context)
    assert context["path"] == a
    assert context["nodes"] == ["refund", "capture"]
    assert [f["line"] for f in context["findings"]] == [12, 30, 50]


def test_the_batch_stops_at_the_findings_bound_but_always_takes_the_first(tmp_path: Path) -> None:
    a = f"{BOOK}/a.md"
    big = range(1, MAX_BATCH_FINDINGS + 2)
    worklist = _worklist(tmp_path, _row("weak-check", a, "refund", *big), _row("unminted-claim", a, "x", 1))

    pick = select_item(LOG, str(worklist))

    assert pick.batch == []
    assert _statuses(worklist) == ["active", "pending"]


def test_a_crashed_batch_reforms_on_the_re_pick(tmp_path: Path) -> None:
    a = f"{BOOK}/a.md"
    worklist = _worklist(tmp_path, _row("dangling-link", a, "refund", 3), _row("weak-check", a, "refund", 9))
    first = select_item(LOG, str(worklist))

    again = select_item(LOG, str(worklist))

    assert again.current_item["target"] == first.current_item["target"]
    assert [r["target"] for r in again.batch] == [r["target"] for r in first.batch]


def test_record_closes_every_row_the_turn_took(tmp_path: Path) -> None:
    a = f"{BOOK}/a.md"
    worklist = _worklist(
        tmp_path,
        _row("dangling-link", a, "refund", 3),
        _row("weak-check", a, "refund", 9),
        _row("weak-check", f"{BOOK}/b.md", "refund", 9),
    )
    pick = select_item(LOG, str(worklist))

    recorded = record(LOG, str(worklist), pick.current_item, [], doc_status="documented",
                      batch=pick.batch)

    assert _statuses(worklist) == ["done", "done", "pending"]
    assert recorded.pending_count == 1


def test_the_prompt_carries_one_fragment_per_code_in_the_batch() -> None:
    codes = ["missing-placement", "weak-check"]
    rendered = render("main/prompts/repair.md", {
        "item_code": codes[0],
        "item_codes": codes,
        "item_kind": f"fix:{codes[0]}",
        "item_target": f"{BOOK}/a.md#refund#{codes[0]}",
        "item_context": "{}",
        "service": "acme",
        "features_root": BOOK,
    }, WORKFLOW_DIR)

    remedies = rendered.split("Where the rule bites")[1]
    for code in codes:
        assert f"### `{code}`" in remedies, f"{code}'s fragment is missing from a batched prompt"
    assert "ostler-okf/references/falsifiable-verification.md" in rendered


def test_a_batched_turn_is_not_the_lowest_tier() -> None:
    row = _row("dangling-link", f"{BOOK}/a.md", "refund", 3)
    other = _row("weak-check", f"{BOOK}/a.md", "refund", 9) | {"attempts": 2}

    assert repair_power(row, row["context"]) == "low"
    assert repair_power(row, row["context"], [row]) == "medium"
    assert repair_power(row, row["context"], [other]) == "high"
