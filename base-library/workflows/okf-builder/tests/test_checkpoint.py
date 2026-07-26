from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "checkpoint.py"
SPEC = importlib.util.spec_from_file_location("okf_checkpoint", SCRIPT)
assert SPEC and SPEC.loader
checkpoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checkpoint)


def test_doctor_filters_unrelated_repository_findings(tmp_path, monkeypatch):
    service = tmp_path / "docs/features/api"
    service.mkdir(parents=True)
    report = {
        "findings": [
            {"severity": "error", "path": "docs/specs/old/plan.md", "message": "old"},
            {"severity": "error", "path": "docs/features/api/http/server.md", "message": "api"},
            {"severity": "warn", "path": "docs/features/api/http/server.md", "message": "warning"},
            {"severity": "error", "path": "docs/features/web/gui/home.md", "message": "web"},
        ]
    }

    class Result:
        stdout = json.dumps(report)

    monkeypatch.setattr(checkpoint.subprocess, "run", lambda *args, **kwargs: Result())

    findings, rendered = checkpoint._doctor_for_features(str(tmp_path), str(service))

    assert [finding["message"] for finding in findings] == ["api"]
    assert "old" not in rendered


def _finding(path: str, line: int, code: str) -> dict:
    return {"severity": "error", "path": path, "line": line, "code": code, "message": code}


def test_repair_items_are_one_per_file_not_one_per_run():
    """A book with many findings must queue many repairs; packing them into one blob dropped most."""
    findings = [
        _finding("a.md", 6, "missing-required-bullet"),
        _finding("a.md", 40, "missing-required-bullet"),
        _finding("b.md", 12, "dangling-link"),
        _finding("c.md", 3, "missing-anchor"),
    ]

    items = checkpoint._repair_items(findings, rnd=2)

    assert len(items) == 3  # a.md's two nodes are one repair, not two
    a = next(i for i in items if "a.md" in i["target"])
    assert json.loads(a["context"]) == findings[:2]  # the file's findings, whole and untruncated


def test_one_files_findings_batch_into_a_single_item():
    """Per-node items made a component file with many findings cost one agent turn per node,
    each re-reading the same source to answer the same question."""
    findings = [_finding("nav.md", line, "missing-required-bullet") for line in range(1, 21)]

    items = checkpoint._repair_items(findings, rnd=1)

    assert len(items) == 1
    assert len(json.loads(items[0]["context"])) == 20


def test_a_large_file_splits_into_bounded_chunks():
    """The batch is capped: past a point one huge item invites a shallow pass over its tail."""
    cap = checkpoint.MAX_FINDINGS_PER_ITEM
    findings = [_finding("nav.md", line, "missing-required-bullet") for line in range(1, cap * 2 + 2)]

    items = checkpoint._repair_items(findings, rnd=1)

    assert len(items) == 3  # cap + cap + 1
    assert [len(json.loads(i["context"])) for i in items] == [cap, cap, 1]
    assert len({i["target"] for i in items}) == 3  # distinct, so none is deduped away
    # every finding survives the split — the whole point of not truncating
    assert sum(len(json.loads(i["context"])) for i in items) == len(findings)


def test_findings_are_ordered_by_line_so_the_agent_works_top_down():
    items = checkpoint._repair_items([
        _finding("a.md", 90, "invalid-role"),
        _finding("a.md", 12, "missing-required-bullet"),
    ], rnd=1)

    assert [f["line"] for f in json.loads(items[0]["context"])] == [12, 90]


def test_missing_required_bullet_is_a_backfill_not_a_fixup():
    """The finding names the key but not the value — that needs source, so it must not be
    filed as a mechanical repair that would satisfy it with an empty stub."""
    items = checkpoint._repair_items([
        _finding("screen.md", 6, "missing-required-bullet"),
        _finding("other.md", 9, "dangling-link"),
    ], rnd=1)

    assert len(items) == 2  # both classified, neither dropped
    assert next(i["kind"] for i in items if "screen.md" in i["target"]) == "backfill"
    assert next(i["kind"] for i in items if "other.md" in i["target"]) == "fixup"


def test_a_file_mixing_finding_kinds_is_grounded():
    """If any finding in the file needs source, the whole item does — the agent opens it once."""
    items = checkpoint._repair_items([
        _finding("s.md", 6, "dangling-link"),
        _finding("s.md", 9, "missing-required-bullet"),
    ], rnd=1)

    assert len(items) == 1
    assert items[0]["kind"] == "backfill"


def test_repair_targets_carry_the_round_so_survivors_requeue():
    """record.py dedups on (kind, target); without the round a finding that survived its repair
    would be deduped away as already-seen and never retried."""
    first = checkpoint._repair_items([_finding("a.md", 6, "dangling-link")], rnd=1)
    second = checkpoint._repair_items([_finding("a.md", 6, "dangling-link")], rnd=2)

    assert first[0]["target"] != second[0]["target"]
