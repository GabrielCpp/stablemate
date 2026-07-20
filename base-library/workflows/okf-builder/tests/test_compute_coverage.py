"""compute-coverage: a verdict it cannot compute is never a pass.

The node replaced a value the `recheck` agent emitted about its own work. What matters is not
that it reports a number, but that every way of failing to get one reports "no".
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "compute-coverage.py"
SPEC = importlib.util.spec_from_file_location("okf_compute_coverage", SCRIPT)
assert SPEC and SPEC.loader
compute = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compute)


def run(argv, monkeypatch, capsys) -> dict:
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        compute.main(logging.getLogger("test"))
    return json.loads(capsys.readouterr().out)


def test_no_inventory_is_not_a_pass(tmp_path, monkeypatch, capsys):
    out = run(["compute-coverage.py", str(tmp_path), "", "api", "", ""], monkeypatch, capsys)
    assert out["coverage_complete"] == "no"
    assert "nothing to join" in out["coverage_error"]


def test_an_unreadable_inventory_is_not_a_pass(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "inv.json"
    bad.write_text("{not json")
    out = run(["compute-coverage.py", str(tmp_path), "", "api", str(bad), ""],
              monkeypatch, capsys)
    assert out["coverage_complete"] == "no"
    assert out["coverage_error"]


def test_an_empty_inventory_is_not_a_pass(tmp_path, monkeypatch, capsys):
    """Zero units is the shape a missing book and a finished one share.

    This is the §1.4 failure at its source: an unreadable language emitted zero units with
    zero errors, every unit in an empty list is covered, and the run declared the book
    complete having documented nothing.
    """
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"units": [], "sourceRoot": "x", "excludes": [], "errors": []}))
    out = run(["compute-coverage.py", str(tmp_path), "", "api", str(inv), ""],
              monkeypatch, capsys)
    assert out["coverage_complete"] == "no"


def test_the_anchor_records_the_source_root_as_the_repo_sees_it(tmp_path):
    """`coverage.json` is committed, so an absolute path would make it machine-local.

    §10.5 rebuilds the whole book when the anchor's `sourceRoot` no longer matches the config —
    so an absolute path means every checkout but the one that wrote it reads a valid anchor as
    stale.
    """
    assert compute._relative_source(str(tmp_path / "report"), str(tmp_path)) == "report"
    assert compute._relative_source(str(tmp_path / "a" / "b"), str(tmp_path)) == "a/b"


def test_a_source_root_outside_the_repo_keeps_what_it_has(tmp_path):
    outside = str(Path(tmp_path).parent / "elsewhere")
    assert compute._relative_source(outside, str(tmp_path)) == outside


def test_a_blind_inventory_is_not_a_pass(tmp_path, monkeypatch, capsys):
    """Units it could read, plus an error for a language it could not: still not complete."""
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({
        "units": [], "sourceRoot": "x", "excludes": [],
        "errors": ["unreadable source: .rb (12 files)"]}))
    out = run(["compute-coverage.py", str(tmp_path), "", "api", str(inv), ""],
              monkeypatch, capsys)
    assert out["coverage_complete"] == "no"
    assert "unreadable" in out["coverage_error"]


# ── the re-scan counter is this node's, not the checkpoint's ──────────────────────────

def test_the_rescan_counter_advances_on_every_exit(tmp_path, monkeypatch, capsys):
    """`guard_rounds` bounds the coverage re-scan, so only this node may advance its counter.

    It used to read `round`, which `checkpoint` bumps on every doctor pass — including the
    fixup re-drains, which are a different loop. A build that took 40 fixup rounds to get
    doctor green reached the guard at round=41 and failed on its first clean checkpoint,
    having never run a single coverage re-scan. The cap reported "the coverage check would
    not converge" about a check that had not run once.

    The error exits must carry the increment too: a re-scan that fails the same way every
    pass has to reach the bound, not reset it.
    """
    out = run(["compute-coverage.py", str(tmp_path), "", "api", "", "", "4"],
              monkeypatch, capsys)
    assert out["coverage_error"]          # an early exit, before any coverage was computed
    assert out["rescan_round"] == 5       # and it still advanced the bound


def test_the_rescan_counter_starts_at_one(tmp_path, monkeypatch, capsys):
    """A missing or unparseable counter starts the loop, it does not disable the bound."""
    for argv_tail in ([], [""], ["not-a-number"]):
        out = run(["compute-coverage.py", str(tmp_path), "", "api", "", *argv_tail],
                  monkeypatch, capsys)
        assert out["rescan_round"] == 1
