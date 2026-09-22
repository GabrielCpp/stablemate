"""A repair turn that ran out of step budget keeps its rows open for a stronger turn."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workhorse.templates import render

import workhorse_workflows
from workhorse_workflows.okf_builder.main.flow import (
    REPAIR_PROFILE,
    REPAIR_STEPS,
    repair_power,
    repair_profile,
)
from workhorse_workflows.okf_builder.shared.schemas import Recorded
from workhorse_workflows.okf_builder.shared.worklist import MAX_TARGET_ATTEMPTS, record

WORKFLOW_DIR = Path(workhorse_workflows.__file__).parent / "okf_builder"
BOOK = "docs/features/acme"
LOG = logging.getLogger("t")


def _row(code: str, node: str, *, attempts: int = 0) -> dict:
    return {
        "kind": f"fix:{code}",
        "target": f"{BOOK}/a.md#{node}#{code}",
        "status": "pending",
        "attempts": attempts,
        "context": json.dumps({"code": code, "node": node, "path": f"{BOOK}/a.md"}),
    }


def _worklist(tmp_path: Path, *rows: dict) -> Path:
    path = tmp_path / "acme.worklist.json"
    path.write_text(json.dumps({"items": list(rows)}))
    return path


def _items(path: Path) -> list[dict]:
    return json.loads(path.read_text())["items"]


def _record(path: Path, current: dict, batch: list[dict], **kwargs) -> Recorded:
    return record(
        LOG, str(path), current, [], doc_status="partial", batch=batch, **kwargs
    )


def test_a_partial_turn_leaves_its_whole_batch_pending(tmp_path: Path) -> None:
    first = _row("weak-check", "refund")
    second = _row("dangling-link", "refund")
    worklist = _worklist(tmp_path, first, second)

    recorded = _record(worklist, first, [second], keep_open=True)

    assert [row["status"] for row in _items(worklist)] == ["pending", "pending"]
    assert recorded.pending_count == 2
    assert recorded.done_count == 0


def test_a_partial_turn_counts_an_attempt_so_the_next_one_is_stronger(tmp_path: Path) -> None:
    row = _row("weak-check", "refund")
    worklist = _worklist(tmp_path, row)
    assert repair_power(row, row["context"]) == "low"

    _record(worklist, row, [], keep_open=True)

    reopened = _items(worklist)[0]
    assert reopened["attempts"] == 1
    assert repair_power(reopened, reopened["context"]) == "medium"
    assert REPAIR_STEPS["medium"] > REPAIR_STEPS["low"]


def test_a_row_that_never_finishes_blocks_instead_of_looping(tmp_path: Path) -> None:
    row = _row("weak-check", "refund", attempts=MAX_TARGET_ATTEMPTS - 1)
    worklist = _worklist(tmp_path, row)

    recorded = _record(worklist, row, [], keep_open=True)

    blocked = _items(worklist)[0]
    assert blocked["status"] == "blocked"
    assert blocked["blocked_reason"]
    assert recorded.blocked_count == 1


def test_a_finished_turn_still_closes_its_batch(tmp_path: Path) -> None:
    first = _row("weak-check", "refund")
    second = _row("dangling-link", "refund")
    worklist = _worklist(tmp_path, first, second)

    record(LOG, str(worklist), first, [], doc_status="documented", batch=[second])

    assert [row["status"] for row in _items(worklist)] == ["done", "done"]


def test_the_step_budget_rides_the_power_tier() -> None:
    assert repair_profile("low").steps == REPAIR_STEPS["low"]
    assert repair_profile("high").steps == REPAIR_STEPS["high"]
    assert repair_profile("nonsense").steps == REPAIR_STEPS["medium"]
    assert repair_profile("low").name == REPAIR_PROFILE.name
    assert repair_profile("low").disable_mcp == REPAIR_PROFILE.disable_mcp
    assert REPAIR_PROFILE.steps is None


def test_the_prompt_tells_the_turn_what_its_budget_buys() -> None:
    rendered = render("main/prompts/repair.md", {
        "item_code": "weak-check",
        "item_codes": ["weak-check"],
        "item_kind": "fix:weak-check",
        "item_target": f"{BOOK}/a.md#refund#weak-check",
        "item_context": "{}",
        "step_budget": 20,
        "service": "acme",
        "features_root": BOOK,
    }, WORKFLOW_DIR)

    assert "at most 20 tool-using steps" in rendered
    assert "partial" in rendered


if __name__ == "__main__":
    import tempfile

    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        if fn.__code__.co_argcount:
            with tempfile.TemporaryDirectory() as tmp:
                fn(Path(tmp))
        else:
            fn()
        print(f"ok {name}")
