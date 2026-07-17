"""validate-partition.py + emit-artifacts.py — losslessness gate and author's contract."""
from __future__ import annotations

import json

from tests.conftest import init_repo, run_script, write_inventory, write_partition

INV = "docs/survey/inventory.json"
PART = "docs/survey/partition.yaml"
BACKLOG = "docs/backlog.md"
MANIFEST = "docs/survey/unit-manifest.json"


def std_inventory(repo):
    write_inventory(repo, [
        {"id": "src/a", "status": "assessed"},
        {"id": "src/b", "status": "assessed"},
        {"id": "src/c", "status": "clean"},
        {"id": "src/d", "status": "blocked"},
    ])


# ── validate-partition.py ───────────────────────────────────────────────────────────────

def test_lossless_partition_passes(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    write_partition(tmp_path, [
        {"id": "fix-frob", "units": ["src/a", "src/b"]},
    ])
    out = run_script("validate-partition.py", PART, INV, repo=tmp_path)
    assert out["partition_ok"] == "yes", out["partition_errors"]


def test_orphaned_assessed_unit_fails(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    write_partition(tmp_path, [{"id": "fix-frob", "units": ["src/a"]}])
    out = run_script("validate-partition.py", PART, INV, repo=tmp_path)
    assert out["partition_ok"] == "no"
    assert "'src/b' appears in NO cluster" in out["partition_errors"]


def test_unknown_and_workless_units_fail(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    write_partition(tmp_path, [
        {"id": "fix-frob", "units": ["src/a", "src/b", "src/nope", "src/c"]},
    ])
    out = run_script("validate-partition.py", PART, INV, repo=tmp_path)
    assert out["partition_ok"] == "no"
    assert "not in the inventory" in out["partition_errors"]
    assert "whose status is 'clean'" in out["partition_errors"]


def test_structural_cluster_problems_fail(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    write_partition(tmp_path, [
        {"id": "fix-frob", "units": ["src/a"]},
        {"id": "fix-frob", "strategy": "sideways", "units": ["src/b"]},
    ])
    out = run_script("validate-partition.py", PART, INV, repo=tmp_path)
    assert out["partition_ok"] == "no"
    assert "duplicate id" in out["partition_errors"]
    assert "sideways" in out["partition_errors"]


def test_missing_partition_file_fails(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    out = run_script("validate-partition.py", PART, INV, repo=tmp_path)
    assert out["partition_ok"] == "no"
    assert "partitioner must write it" in out["partition_errors"]


# ── emit-artifacts.py ───────────────────────────────────────────────────────────────────

def emit(repo):
    return run_script("emit-artifacts.py", PART, INV, BACKLOG, MANIFEST, repo=repo)


def test_emits_fenced_backlog_section_and_manifest(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    write_partition(tmp_path, [
        {"id": "later", "order": 2, "units": ["src/b"], "strategy": "dedicated"},
        {"id": "first", "order": 1, "units": ["src/a", "src/b"],
         "notes": "shared primitive first"},
    ])
    out = emit(tmp_path)
    assert out["emit_ok"] == "yes", out["emit_errors"]
    assert out["bullet_count"] == 2

    backlog = (tmp_path / BACKLOG).read_text()
    assert "<!-- surveyor:begin" in backlog and "<!-- surveyor:end -->" in backlog
    assert "- [survey-first]" in backlog and "- [survey-later]" in backlog
    assert backlog.index("[survey-first]") < backlog.index("[survey-later]")  # order honored
    assert "shared primitive first" in backlog

    manifest = json.loads((tmp_path / MANIFEST).read_text())
    by_id = {u["id"]: u for u in manifest["units"]}
    assert by_id["src/a"]["bullets"] == ["survey-first"]
    assert sorted(by_id["src/b"]["bullets"]) == ["survey-first", "survey-later"]
    assert by_id["src/c"]["bullets"] == []  # clean — no coverage demanded
    assert by_id["src/d"]["bullets"] == []  # blocked — a gap, not backlog work
    assert manifest["generatedBy"] == "surveyor"


def test_reemit_replaces_the_fence_and_preserves_human_content(tmp_path):
    init_repo(tmp_path)
    std_inventory(tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / BACKLOG).write_text(
        "# Backlog\n\n- [b1] human bullet\n\n## Filed by coder\n\n- [c1] coder bullet\n",
        encoding="utf-8",
    )
    write_partition(tmp_path, [{"id": "first", "units": ["src/a", "src/b"]}])
    emit(tmp_path)
    write_partition(tmp_path, [{"id": "second", "units": ["src/a", "src/b"]}])
    emit(tmp_path)

    backlog = (tmp_path / BACKLOG).read_text()
    assert "- [b1] human bullet" in backlog
    assert "- [c1] coder bullet" in backlog
    assert "- [survey-second]" in backlog
    assert "- [survey-first]" not in backlog  # replaced, not appended
    assert backlog.count("<!-- surveyor:begin") == 1
