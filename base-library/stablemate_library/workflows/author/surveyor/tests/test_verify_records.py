"""verify-records.py — the deterministic survey-coverage gate."""
from __future__ import annotations


from .conftest import git_repo, init_repo, run_script, write_inventory, write_record

INV = "docs/survey/inventory.json"
FINDINGS = "docs/survey/findings"


def verify(repo):
    return run_script("verify-records.py", INV, FINDINGS, "", repo=repo)


def test_all_units_recorded_passes(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"},
                               {"id": "src/b", "status": "clean"}])
    write_record(tmp_path, "src/a")
    write_record(tmp_path, "src/b", status="clean", findings=[])
    out = verify(tmp_path)
    assert out["verify_ok"] == "yes", out["verify_errors"]
    assert "2 unit(s)" in out["verify_report"]


def test_missing_inventory_skips(tmp_path):
    init_repo(tmp_path)
    assert verify(tmp_path)["verify_ok"] == "skip"


def test_pending_unit_fails(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a"}])
    out = verify(tmp_path)
    assert out["verify_ok"] == "no"
    assert "[pending]" in out["verify_errors"]


def test_missing_and_disagreeing_records_fail(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"},
                               {"id": "src/b", "status": "clean"}])
    write_record(tmp_path, "src/b", status="assessed")  # disagrees with inventory
    out = verify(tmp_path)
    assert out["verify_ok"] == "no"
    assert "[missing-record] 'src/a'" in out["verify_errors"]
    assert "[status-mismatch] 'src/b'" in out["verify_errors"]


def test_blocked_unit_is_an_open_gap_until_accepted(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "blocked"}])
    write_record(tmp_path, "src/a", status="blocked", findings=[],
                 open_gaps=["needs prod credentials"])
    out = verify(tmp_path)
    assert out["verify_ok"] == "no"
    assert "[blocked] 'src/a'" in out["verify_errors"]
    assert "needs prod credentials" in out["verify_errors"]

    # Operator records the accepted disposition → the gap is owned, gate passes.
    write_record(tmp_path, "src/a", status="blocked", findings=[],
                 open_gaps=["needs prod credentials"], disposition="accepted")
    assert verify(tmp_path)["verify_ok"] == "yes"


def test_invalid_record_fails(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"}])
    rec = tmp_path / FINDINGS / "src-a.md"
    rec.parent.mkdir(parents=True)
    rec.write_text("garbage\n", encoding="utf-8")
    out = verify(tmp_path)
    assert out["verify_ok"] == "no"
    assert "[invalid-record] 'src/a'" in out["verify_errors"]


def test_dropped_unit_vs_committed_baseline_fails(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"},
                               {"id": "src/b", "status": "assessed"}])
    write_record(tmp_path, "src/a")
    write_record(tmp_path, "src/b")
    git_repo(tmp_path)

    # Drop src/b from the frozen list (no split lineage, record or not — it's a drop).
    write_inventory(tmp_path, [{"id": "src/a", "status": "assessed"}])
    out = verify(tmp_path)
    assert out["verify_ok"] == "no"
    assert "[dropped-unit] 'src/b'" in out["verify_errors"]


def test_split_lineage_is_not_a_drop(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/big", "status": "pending"}])
    git_repo(tmp_path)

    # The parent was split: children extend its path — detectable lineage, not a drop.
    write_inventory(tmp_path, [{"id": "src/big/a.ts", "kind": "file", "status": "clean"},
                               {"id": "src/big/b.ts", "kind": "file", "status": "clean"}])
    write_record(tmp_path, "src/big/a.ts", status="clean", findings=[], kind="file")
    write_record(tmp_path, "src/big/b.ts", status="clean", findings=[], kind="file")
    out = verify(tmp_path)
    assert out["verify_ok"] == "yes", out["verify_errors"]


def test_no_git_baseline_skips_the_shrinkage_check(tmp_path):
    init_repo(tmp_path)  # no git repo at all
    write_inventory(tmp_path, [{"id": "src/a", "status": "clean"}])
    write_record(tmp_path, "src/a", status="clean", findings=[])
    assert verify(tmp_path)["verify_ok"] == "yes"
