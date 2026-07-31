"""Tests for run identity and resume selection (`workhorse.rundir`).

Auto-resume-in-place is the default and has no flag: each `(workflow, run-id)` pair
maps to one stable run dir, the id is derived from `--params` when none is given, and
a run that already reached a terminal node is started fresh rather than replayed. The
rules live in `workhorse.rundir` because the driver has to obey exactly the same ones
as the CLI — `--resume-latest` would otherwise mean two different things.

Run: uv run python tests/test_resume_auto.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from workhorse.rundir import auto_resolve, derive_run_id, find_latest_resumable

m = importlib.import_module("workhorse.main")


class _StubRegistry:
    """Stands in for the resolved Registry — these tests never reach the driver."""

    name = "research"


def _make_run(runs_dir: Path, name: str, *, terminal, with_checkpoint=True, with_run_json=True):
    d = runs_dir / name
    d.mkdir(parents=True)
    if with_checkpoint:
        (d / "checkpoint.json").write_text(json.dumps({"state": "select_gate", "params": {}}))
    if with_run_json:
        (d / "run.json").write_text(json.dumps({
            "workflow": "research", "run_id": name, "terminal": terminal,
        }))
    return d


def test_find_latest_resumable_picks_unfinished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal="fail")          # finished -> skip
        time.sleep(0.01)
        stopped = _make_run(runs, "research-002", terminal=None)  # killed mid-flight -> resumable
        got = find_latest_resumable(runs)
        assert got == stopped, got


def test_find_latest_resumable_none_when_all_finished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal="terminal")  # done
        _make_run(runs, "research-002", terminal="fail")      # fail
        assert find_latest_resumable(runs) is None


def test_find_latest_resumable_ignores_dirs_without_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal=None, with_checkpoint=False)
        assert find_latest_resumable(runs) is None


def test_find_latest_resumable_picks_newest_of_several_unfinished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal=None)
        time.sleep(0.01)
        newest = _make_run(runs, "research-002", terminal=None)
        assert find_latest_resumable(runs) == newest


def test_auto_resolve_single_stable_dir_per_program():
    """Auto-resume uses one fixed dir per (workflow, run-id); it resumes that dir when
    it holds a checkpoint, else returns None so the caller starts fresh IN that same
    dir."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        # no dir yet -> start fresh, but the run id is the stable program name
        rid, resume = auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid == "grammar-semantics"
        assert resume is None

        # create the stable dir with a checkpoint -> resume it in place
        stable = runs / "research-grammar-semantics"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"state": "implement", "params": {}}))
        rid2, resume2 = auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid2 == "grammar-semantics"
        assert resume2 == stable  # same single folder, continued


def test_auto_resolve_skips_terminal_run():
    """A stable dir whose run already finished (run.json terminal set) is NOT
    resumed — re-running starts a new run rather than replaying the finished one
    (mirrors find_latest_resumable). Without this, a coder run that reached its
    terminal state would no-op on the next launch."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        stable = runs / "coder-default"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"state": "merge_final", "params": {}}))
        # No run.json (or terminal=None) -> resumable.
        assert auto_resolve(runs, "coder", run_id="default")[1] == stable
        # run.json marks it terminal -> start fresh (resume None) in the same dir.
        (stable / "run.json").write_text(json.dumps({"workflow": "coder", "terminal": "terminal"}))
        rid, resume = auto_resolve(runs, "coder", run_id="default")
        assert rid == "default"
        assert resume is None


def test_auto_resolve_run_id_precedence():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        # No run_id → "default".
        assert auto_resolve(runs, "research")[0] == "default"
        # Explicit run_id is used verbatim.
        assert auto_resolve(runs, "research", run_id="given")[0] == "given"


def test_derive_run_id_explicit_wins_and_no_params_is_default():
    # Explicit --run-id is always used verbatim, params or not.
    assert derive_run_id("given", {"service": "api"}) == "given"
    # No params → None → caller's "default".
    assert derive_run_id(None, None) is None
    assert derive_run_id(None, {}) is None


def test_derive_run_id_digests_params_stably_and_distinctly():
    report = derive_run_id(None, {"service": "report", "source_path": "report"})
    api = derive_run_id(None, {"service": "api", "source_path": "api"})
    # Distinct params → distinct ids (no collision on one 'default').
    assert report != api
    assert report.startswith("p") and api.startswith("p")
    # Same params (key order irrelevant) → SAME id, so auto-resume still lands on
    # the existing checkpoint on a plain re-run / reboot.
    again = derive_run_id(None, {"source_path": "report", "service": "report"})
    assert again == report


def test_derive_run_id_routes_distinct_targets_to_distinct_dirs():
    """The end-to-end footgun: two targets under no explicit run-id must resolve to
    different stable dirs, and each resumes its own checkpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        rid_report = derive_run_id(None, {"service": "report"})
        rid_api = derive_run_id(None, {"service": "api"})
        assert rid_report != rid_api
        # report has an unfinished checkpoint; api has none → api starts fresh
        # instead of resuming report's run.
        _make_run(runs, f"okf-builder-{rid_report}", terminal=None)
        assert auto_resolve(runs, "okf-builder", rid_report)[1] is not None
        assert auto_resolve(runs, "okf-builder", rid_api)[1] is None


def test_auto_flag_is_gone():
    """--auto must not exist anymore (auto is the default, not an opt-in)."""
    with patch("sys.argv", ["workhorse", "--workflow", "research", "--auto"]):
        try:
            m.main()
            raise AssertionError("--auto should no longer be a recognized flag")
        except SystemExit as e:
            assert e.code == 2, "argparse should reject the unknown --auto flag"


def test_resume_latest_still_errors_when_none():
    """Existing strict --resume-latest behavior is preserved (errors if none)."""
    called = {"run": False}

    def fake_run_pyflow(*a, **k):
        called["run"] = True
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        runs.mkdir()
        exit_code = None
        with patch.object(m, "run_pyflow", fake_run_pyflow), patch.object(
            m, "_packaged_registry", lambda spec: _StubRegistry()
        ), patch(
            "sys.argv",
            ["workhorse", "--workflow", "research", "--runs-dir", str(runs), "--resume-latest"],
        ):
            try:
                m.main()
            except SystemExit as e:
                exit_code = e.code
    assert called["run"] is False, "the driver should not be entered with nothing to resume"
    assert exit_code == 1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
