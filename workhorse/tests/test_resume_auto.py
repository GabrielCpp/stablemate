"""Tests for run identity and resume selection (`workhorse.rundir`)."""
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
    """Stands in for the bound Registry — these tests never reach the driver."""

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
        _make_run(runs, "research-001", terminal="fail")
        time.sleep(0.01)
        stopped = _make_run(runs, "research-002", terminal=None)
        got = find_latest_resumable(runs)
        assert got == stopped, got


def test_find_latest_resumable_none_when_all_finished():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        _make_run(runs, "research-001", terminal="terminal")
        _make_run(runs, "research-002", terminal="fail")
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
    """Auto-resume uses one fixed dir per (workflow, run-id); it resumes that dir when it holds a checkpoint, else returns None so the caller starts fresh IN that same dir."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        rid, resume = auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid == "grammar-semantics"
        assert resume is None

        stable = runs / "research-grammar-semantics"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"state": "implement", "params": {}}))
        rid2, resume2 = auto_resolve(runs, "research", run_id="grammar-semantics")
        assert rid2 == "grammar-semantics"
        assert resume2 == stable


def test_auto_resolve_skips_terminal_run():
    """A stable dir whose run already finished (run.json terminal set) is NOT resumed — re-running starts a new run rather than replaying the finished one (mirrors find_latest_resumable)."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        stable = runs / "coder-default"
        stable.mkdir()
        (stable / "checkpoint.json").write_text(json.dumps({"state": "merge_final", "params": {}}))
        assert auto_resolve(runs, "coder", run_id="default")[1] == stable
        (stable / "run.json").write_text(json.dumps({"workflow": "coder", "terminal": "terminal"}))
        rid, resume = auto_resolve(runs, "coder", run_id="default")
        assert rid == "default"
        assert resume is None


def test_auto_resolve_run_id_precedence():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        assert auto_resolve(runs, "research")[0] == "default"
        assert auto_resolve(runs, "research", run_id="given")[0] == "given"


def test_derive_run_id_explicit_wins_and_no_params_is_default():
    assert derive_run_id("given", {"service": "api"}) == "given"
    assert derive_run_id(None, None) is None
    assert derive_run_id(None, {}) is None


def test_derive_run_id_digests_params_stably_and_distinctly():
    report = present(derive_run_id(None, {"service": "report", "source_path": "report"}))
    api = present(derive_run_id(None, {"service": "api", "source_path": "api"}))
    assert report != api
    assert report.startswith("p") and api.startswith("p")
    again = derive_run_id(None, {"source_path": "report", "service": "report"})
    assert again == report


def test_derive_run_id_routes_distinct_targets_to_distinct_dirs():
    """The end-to-end footgun: two targets under no explicit run-id must resolve to different stable dirs, and each resumes its own checkpoint."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        rid_report = derive_run_id(None, {"service": "report"})
        rid_api = derive_run_id(None, {"service": "api"})
        assert rid_report != rid_api
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
    """The only way this feature fails silently."""
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
    """The backend and the config file are resolved at the process edge rather than held by the run, and a supervisor re-spawning this line hours later is a fresh process with a fresh environment — so what the environment would have said has to be in the argv."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "research-shakedown"
        cfg = Path(tmp) / "stablemate.toml"
        cfg.write_text(
            '[profiles.cheap]\ncli = "claude"\n[profiles.cheap.default]\nmodel = "haiku"\n'
        )
        argv = resume_argv(
            "workhorse-research", run_dir,
            profile="cheap", config_path=str(cfg),
        )
        assert argv[:4] == ["workhorse-research", "run", "--resume-run", str(run_dir)]
        assert "--params" not in argv and "--params-file" not in argv

        run_dir.mkdir(parents=True)
        (run_dir / "checkpoint.json").write_text(json.dumps({"state": "s", "params": {}}))
        resumed = _invocation(argv[1:])

        assert resumed.config.backend.name == "claude"
        assert resumed.config.profile == "cheap"


def test_the_recorded_resume_command_of_a_profiled_run_is_accepted_by_the_cli():
    """The launch record names both what the process resolved: the backend *and* the profile."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "research-shakedown"
        cfg = Path(tmp) / "stablemate.toml"
        cfg.write_text(
            '[profiles.cheap]\ncli = "codex"\n[profiles.cheap.default]\nmodel = "m"\n'
        )
        argv = resume_argv(
            "workhorse-research", run_dir,
            cli="codex", profile="cheap", config_path=str(cfg),
        )
        run_dir.mkdir(parents=True)
        (run_dir / "checkpoint.json").write_text(json.dumps({"state": "s", "params": {}}))
        resumed = _invocation(argv[1:])

        assert resumed.config.backend.name == "codex"
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
