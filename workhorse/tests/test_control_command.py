"""`workhorse-<name> control reload` — the operator's half of a live reload.

The run being reloaded is a different process, usually in a different container, so this
command is exactly three things: work out which run dir is meant, write the request file
atomically, and report what that run appeared to be doing. What it must *not* do is
block waiting for the reload to land — the whole point is a one-line nudge that ends,
not a second foreground process to watch.

The tests below pin the two halves that fail quietly: the request file carries the flags
that were typed (a `--at-boundary` silently dropped would cut a turn the operator asked
to let finish), and the run is resolved by every name the operator already has for it.

Run: uv run python tests/test_control_command.py   (or via pytest)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from workhorse import reload  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.cli import main as cli_main  # noqa: E402
from workhorse.pyflow.registry import Registry  # noqa: E402
from workhorse.records import PyflowCheckpoint, RunRecord  # noqa: E402


def _run_dir(runs: Path, name: str = "demo-t", *, terminal: str | None = None) -> Path:
    """A run dir with the two files `control` reads: what the run is, and where it is."""
    run_dir = runs / name
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        RunRecord(
            workflow="demo",
            run_id=name.removeprefix("demo-"),
            started_at="2026-01-01T00:00:00+00:00",
            terminal=terminal,
            pid=os.getpid(),
        ).model_dump_json()
    )
    (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text(
        PyflowCheckpoint(state="plan_story", flow="Qa", workflow="demo").model_dump_json()
    )
    return run_dir


def _control(runs: Path, *argv: str) -> None:
    cli_main(["control", *argv], workflow="demo", registry=Registry("demo"))


def _request(run_dir: Path) -> dict:
    return json.loads((run_dir / reload.REQUEST_FILE).read_text())


def test_reload_writes_the_request_the_run_polls_for(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        _control(runs, "reload", "--run", "t", "--runs-dir", str(runs))

        # The default is to cut the turn, because the default reason to reload is that
        # the turn is burning tokens on a flow the operator has already fixed.
        assert _request(run_dir)["core"] is False
        assert _request(run_dir)["at_boundary"] is False
        out = capsys.readouterr().out
        # The report is evidence, not confirmation — it says where the run was, so a
        # request that landed on the wrong run is visible immediately.
        assert "Qa.plan_story" in out, out
        assert f"pid {os.getpid()} is alive" in out, out


def test_the_flags_that_were_typed_are_the_flags_that_are_written() -> None:
    """A dropped `--at-boundary` would cut a turn the operator asked to let land, and a
    dropped `--core` would silently reload half of what was asked for."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        _control(runs, "reload", "--run", "t", "--runs-dir", str(runs), "--core", "--at-boundary")

        assert _request(run_dir) | {"requested_at": ""} == {
            "core": True,
            "at_boundary": True,
            "requested_at": "",
        }


def test_a_run_is_found_by_its_id_its_dir_name_or_its_path() -> None:
    """The three spellings an operator already has in their shell history. A name that
    resumes a run has to be a name that can reload it, or the two commands drift."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        for spec in ("t", "demo-t", str(run_dir)):
            (run_dir / reload.REQUEST_FILE).unlink(missing_ok=True)
            _control(runs, "reload", "--run", spec, "--runs-dir", str(runs))
            assert reload.pending(run_dir) is not None, spec


def test_with_no_run_named_the_newest_unfinished_run_is_taken(capsys) -> None:
    """Worth having and worth bounding: the operator watching one run should not have to
    retype an id they never chose, but a finished run must not absorb the request."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        done = _run_dir(runs, "demo-done", terminal="terminal")
        live = _run_dir(runs, "demo-live")

        _control(runs, "reload", "--runs-dir", str(runs))

        assert reload.pending(live) is not None
        assert reload.pending(done) is None
        assert str(live) in capsys.readouterr().out


def test_a_run_that_does_not_exist_is_an_error_not_a_new_directory(capsys) -> None:
    """`reload.request` would happily create the file under a mistyped path, and the
    operator would be left watching a run that never sees it."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "reload", "--run", "typo", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        assert "no run dir for 'typo'" in capsys.readouterr().err
        assert not (runs / "demo-typo").exists()


def test_a_finished_run_is_told_so_rather_than_being_left_to_look_pending(capsys) -> None:
    """Naming it explicitly still writes the request — the run dir is resumable and the
    request is read on entry — but the report has to say nobody is listening now."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs, "demo-t", terminal="terminal")

        _control(runs, "reload", "--run", "t", "--runs-dir", str(runs))

        assert reload.pending(run_dir) is not None
        assert "already finished" in capsys.readouterr().out
