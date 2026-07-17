"""select-next-unit.py + mark-unit.py + check-inventory.py — the loop's drivers."""
from __future__ import annotations

import json

from tests.conftest import init_repo, run_script, write_inventory, write_record, write_rules

INV = "docs/survey/inventory.json"
FINDINGS = "docs/survey/findings"
RULES = "docs/survey/units.yml"


# ── check-inventory.py: planner precedence ──────────────────────────────────────────────

def test_planner_needed_when_nothing_exists(tmp_path):
    init_repo(tmp_path)
    out = run_script("check-inventory.py", INV, RULES, repo=tmp_path)
    assert out["needs_plan"] == "yes"


def test_pinned_rules_beat_the_planner(tmp_path):
    init_repo(tmp_path)
    write_rules(tmp_path, "rules: []\n")
    out = run_script("check-inventory.py", INV, RULES, repo=tmp_path)
    assert out["needs_plan"] == "no"
    assert "operator-pinned" in out["check_note"]


def test_frozen_inventory_beats_everything(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "u1"}])
    out = run_script("check-inventory.py", INV, RULES, repo=tmp_path)
    assert out["needs_plan"] == "no"
    assert "frozen" in out["check_note"]


# ── select-next-unit.py ─────────────────────────────────────────────────────────────────

def test_selects_first_pending_unit_with_record_path(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [
        {"id": "src/a", "status": "clean"},
        {"id": "src/b", "kind": "file"},
        {"id": "src/c"},
    ])
    out = run_script("select-next-unit.py", INV, FINDINGS, repo=tmp_path)
    assert out["has_unit"] == "yes"
    assert out["unit_id"] == "src/b"
    assert out["unit_kind"] == "file"
    assert out["record_path"] == f"{FINDINGS}/src-b.md"


def test_no_pending_units_ends_the_loop(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"},
                               {"id": "src/b", "status": "blocked"}])
    out = run_script("select-next-unit.py", INV, FINDINGS, repo=tmp_path)
    assert out["has_unit"] == "no"


def test_missing_inventory_ends_the_loop(tmp_path):
    init_repo(tmp_path)
    out = run_script("select-next-unit.py", INV, FINDINGS, repo=tmp_path)
    assert out["has_unit"] == "no"
    assert "expand_inventory" in out["reason"]


# ── mark-unit.py ────────────────────────────────────────────────────────────────────────

def unit_status(repo, unit_id):
    units = json.loads((repo / INV).read_text())["units"]
    return next(u["status"] for u in units if u["id"] == unit_id)


def test_marks_unit_from_validated_record_status(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a"}])
    rec = write_record(tmp_path, "src/a", status="clean", findings=[])
    out = run_script("mark-unit.py", INV, "src/a", str(rec.relative_to(tmp_path)), "",
                     repo=tmp_path)
    assert out["marked"] == "yes"
    assert out["unit_status"] == "clean"
    assert unit_status(tmp_path, "src/a") == "clean"


def test_missing_record_marks_blocked_and_writes_stub(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a"}])
    out = run_script("mark-unit.py", INV, "src/a", f"{FINDINGS}/src-a.md",
                     "assessor never wrote the record", repo=tmp_path)
    assert out["marked"] == "yes"
    assert out["unit_status"] == "blocked"
    assert unit_status(tmp_path, "src/a") == "blocked"
    stub = (tmp_path / FINDINGS / "src-a.md").read_text()
    assert "status: blocked" in stub
    assert "assessor never wrote the record" in stub


def test_invalid_record_marks_blocked_without_clobbering_it(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a"}])
    rec = tmp_path / FINDINGS / "src-a.md"
    rec.parent.mkdir(parents=True)
    rec.write_text("not a record at all\n", encoding="utf-8")
    out = run_script("mark-unit.py", INV, "src/a", f"{FINDINGS}/src-a.md",
                     "unfixable", repo=tmp_path)
    assert out["unit_status"] == "blocked"
    assert rec.read_text() == "not a record at all\n"  # evidence preserved for the gate


def test_unknown_unit_is_reported(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a"}])
    write_record(tmp_path, "src/b")
    out = run_script("mark-unit.py", INV, "src/b", f"{FINDINGS}/src-b.md", "", repo=tmp_path)
    assert out["marked"] == "no"
    assert "not found" in out["mark_note"]
