"""Tests for resume selection (_find_latest_resumable) and the --auto launch mode.

--auto resumes the latest unfinished run if one exists, else starts fresh — so a
stopped/crashed run (incl. one killed during a cap wait) reloads its state and
continues from the last checkpoint, while a first run still starts cleanly.

Run: ./.venv/bin/python tests/test_resume_auto.py   (or via pytest)
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import importlib

m = importlib.import_module("workhorse.main")


def _make_run(runs_dir: Path, name: str, *, terminal, with_checkpoint=True, with_run_json=True):
    d = runs_dir / name
    d.mkdir(parents=True)
    if with_checkpoint:
        (d / "checkpoint.json").write_text(json.dumps({"current_id": "select_gate", "context": {}}))
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
        got = m._find_latest_resumable(runs)
        assert got == stopped, got


def test_find_latest_resumable_none_when_all_finished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal="terminal")  # done
        _make_run(runs, "research-002", terminal="fail")      # fail
        assert m._find_latest_resumable(runs) is None


def test_find_latest_resumable_ignores_dirs_without_checkpoint():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal=None, with_checkpoint=False)
        assert m._find_latest_resumable(runs) is None


def test_find_latest_resumable_picks_newest_of_several_unfinished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal=None)
        time.sleep(0.01)
        newest = _make_run(runs, "research-002", terminal=None)
        assert m._find_latest_resumable(runs) == newest


def test_auto_resolve_single_stable_dir_per_program():
    """--auto uses one fixed dir per (workflow, program); resumes it when it holds
    a checkpoint, else returns None so the caller starts fresh IN that same dir."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        # no dir yet -> start fresh, but the run id is the stable program name
        rid, resume = m._auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid == "grammar-semantics"
        assert resume is None

        # create the stable dir with a checkpoint -> resume it in place
        stable = runs / "research-grammar-semantics"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"current_id": "implement", "context": {}}))
        rid2, resume2 = m._auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid2 == "grammar-semantics"
        assert resume2 == stable  # same single folder, continued


def test_auto_resolve_skips_terminal_run():
    """A stable dir whose run already finished (run.json terminal set) is NOT
    resumed — re-running starts a new run rather than replaying the finished one
    (mirrors _find_latest_resumable). Without this, an epic-coder run that reached
    its terminal node would no-op on the next `make agent-native`."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        stable = runs / "epic-coder-default"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"current_id": "merge_final", "context": {}}))
        # No run.json (or terminal=None) -> resumable.
        assert m._auto_resolve(runs, "epic-coder", run_id="default")[1] == stable
        # run.json marks it terminal -> start fresh (resume None) in the same dir.
        (stable / "run.json").write_text(json.dumps({"workflow": "epic-coder", "terminal": "terminal"}))
        rid, resume = m._auto_resolve(runs, "epic-coder", run_id="default")
        assert rid == "default"
        assert resume is None


def test_auto_resolve_run_id_precedence():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        # No run_id → "default".
        assert m._auto_resolve(runs, "research")[0] == "default"
        # Explicit run_id is used verbatim.
        assert m._auto_resolve(runs, "research", run_id="given")[0] == "given"


def test_main_is_auto_by_default_no_flag():
    """No flag needed: main() runs in auto mode by default (single stable folder,
    resolved inside run())."""
    captured = {}

    def fake_run(workflow_path, runs_dir, resume_run_dir=None, auto=True, run_id=None, params=None, context_manifest=None, flow=None, no_cache=False):
        captured.update(resume_run_dir=resume_run_dir, auto=auto)
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runs = tmp / "runs"
        runs.mkdir()
        wf = tmp / "workflow.yaml"
        wf.write_text("name: research\n")
        with patch.object(m, "run", fake_run), patch(
            "sys.argv",
            ["workhorse", "--workflow", str(wf), "--runs-dir", str(runs)],  # no --auto
        ):
            try:
                m.main()
            except SystemExit as e:
                captured["exit_code"] = e.code
    assert captured["auto"] is True, "auto must be the default with no flag"
    assert captured["resume_run_dir"] is None  # resolved inside run(), not main()
    assert captured["exit_code"] == 0


def test_auto_flag_is_gone():
    """--auto must not exist anymore (auto is the default, not an opt-in)."""
    with tempfile.TemporaryDirectory() as tmp:
        wf = Path(tmp) / "workflow.yaml"
        wf.write_text("name: research\n")
        with patch("sys.argv", ["workhorse", "--workflow", str(wf), "--auto"]):
            try:
                m.main()
                raise AssertionError("--auto should no longer be a recognized flag")
            except SystemExit as e:
                assert e.code == 2, "argparse should reject the unknown --auto flag"


def test_resume_latest_still_errors_when_none():
    """Existing strict --resume-latest behavior is preserved (errors if none)."""
    called = {"run": False}

    def fake_run(*a, **k):
        called["run"] = True
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runs = tmp / "runs"
        runs.mkdir()
        wf = tmp / "workflow.yaml"
        wf.write_text("name: research\n")
        exit_code = None
        with patch.object(m, "run", fake_run), patch(
            "sys.argv",
            ["workhorse", "--workflow", str(wf), "--runs-dir", str(runs), "--resume-latest"],
        ):
            try:
                m.main()
            except SystemExit as e:
                exit_code = e.code
    assert called["run"] is False, "run() should not be called when nothing to resume"
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
