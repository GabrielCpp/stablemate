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

from _fakes import present
from workhorse.pyflow import Registry
from workhorse.rundir import (
    auto_resolve,
    derive_run_id,
    find_latest_resumable,
    resume_argv,
)

cli_mod = importlib.import_module("workhorse.cli")
run_cmd = importlib.import_module("workhorse.cli.run")


class _StubRegistry(Registry):
    """Stands in for the bound Registry — these tests never reach the driver.

    A real `Registry` rather than a look-alike: the CLI's parameter is the type, and
    only the entry point (which these tests never reach) is stubbed out.
    """

    def __init__(self) -> None:
        super().__init__('research')

    def directory(self) -> Path:
        return Path(__file__).resolve().parent


def _main(argv: list[str]) -> None:
    """Drive the console script the way the `research` workflow's own would."""
    cli_mod.main(argv, workflow="research", registry=_StubRegistry())


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
    report = present(derive_run_id(None, {"service": "report", "source_path": "report"}))
    api = present(derive_run_id(None, {"service": "api", "source_path": "api"}))
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
    try:
        _main(["run", "--auto"])
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
        with patch.object(run_cmd, "run_pyflow", fake_run_pyflow):
            try:
                _main(["run", "--runs-dir", str(runs), "--resume-latest"])
            except SystemExit as e:
                exit_code = e.code
    assert called["run"] is False, "the driver should not be entered with nothing to resume"
    assert exit_code == 1


def _invocation(argv: list[str]):
    """Drive the CLI as far as the `RunInvocation` and stop, returning it."""
    seen = {}

    def fake_run_pyflow(invocation, *a, **k):
        seen["it"] = invocation
        return 0

    with patch.object(run_cmd, "run_pyflow", fake_run_pyflow):
        try:
            _main(argv)
        except SystemExit as e:
            assert e.code == 0, e.code
    return seen["it"]


def test_the_recorded_resume_command_parses_back_onto_the_same_run():
    """The only way this feature fails silently. A launch record is written by one
    process and read by another after the first is dead — nothing checks the line in
    between, so a command that no longer parses looks exactly like a command that does
    until the day something tries to resume with it.

    Deliberately launched with `--no-cache`, which is the flag that makes replaying the
    original argv destructive rather than merely wrong: it deletes the run directory
    before starting, so a supervisor that replayed it would destroy the checkpoint it
    was trying to save. The resume line is built, not replayed, and this pins that.
    """
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        launched = _invocation([
            "run", "--runs-dir", str(runs), "--run-id", "shakedown", "--no-cache",
            "--params", json.dumps({"topic": "acme"}),
        ])
        assert launched.no_cache is True
        run_dir = runs / f"research-{launched.run_id}"
        run_dir.mkdir(parents=True)
        (run_dir / "checkpoint.json").write_text(json.dumps({"state": "s", "params": {}}))

        resumed = _invocation(resume_argv("workhorse-research", run_dir)[1:])

        assert resumed.resume_run_dir == run_dir, resumed.resume_run_dir
        assert resumed.no_cache is False, "a resume must never delete the dir it resumes"


def test_the_recorded_resume_command_carries_what_the_checkpoint_does_not_hold():
    """The backend and the config file are resolved at the process edge rather than held
    by the run, and a supervisor re-spawning this line hours later is a fresh process
    with a fresh environment — so what the environment would have said has to be in the
    argv. The params are the other way round: they are in the checkpoint, and replaying
    a `--params-file` would let a stale file win over what the run really holds."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "research-shakedown"
        cfg = Path(tmp) / "stablemate.toml"
        cfg.write_text('[profiles.cheap.default.claude]\nmodel = "haiku"\n')
        argv = resume_argv(
            "workhorse-research", run_dir,
            cli="claude", profile="cheap", config_path=str(cfg),
        )
        assert argv[:4] == ["workhorse-research", "run", "--resume-run", str(run_dir)]
        assert "--params" not in argv and "--params-file" not in argv

        run_dir.mkdir(parents=True)
        (run_dir / "checkpoint.json").write_text(json.dumps({"state": "s", "params": {}}))
        resumed = _invocation(argv[1:])

        assert resumed.config.backend.name == "claude"
        assert resumed.config.profile == "cheap"


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
