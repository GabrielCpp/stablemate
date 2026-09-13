"""`control rewind`, `control resume`, `status --params` and `stop --wait`.

These are the verbs that act on a run nobody is serving, so what they must never do is
act on one somebody is: a rewind under a live driver is overwritten at its next transition,
and a resume beside one is two drivers writing one run dir. The tests below pin that
refusal first, then the halves that fail quietly — a rewind that writes a checkpoint the
resume would reject, a resume that dies in its first second and reports success, a
`--cli` swap that leaves the recorded `--profile` in the line `run` refuses both of.

Run: uv run python tests/test_control_offline.py   (or via pytest)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from workhorse import control  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.cli import main as cli_main  # noqa: E402
from workhorse.cli import offline  # noqa: E402
from workhorse.pyflow import Continue, Done, Registry, Workflow  # noqa: E402
from workhorse.records import LaunchRecord, PyflowCheckpoint, RunRecord  # noqa: E402


class Demo(Workflow):
    target: str = "acme"

    def start(self) -> Continue:
        return Continue(None, self.build, item="G1", budget=3)

    def build(self, item: str, budget: int) -> Continue:
        return Continue(None, self.review, verdict={"ok": True})

    def review(self, verdict: dict, budget: int = 2) -> Done:
        return Done(None)


#: One registry for the module: a flow class belongs to exactly one.
_REGISTRY = Registry("demo").entry_point(Demo)


def _dead_pid() -> int:
    """A pid that answered once and is gone now — a stopped run's `run.json`."""
    child = subprocess.Popen([sys.executable, "-c", ""])
    child.wait()
    return child.pid


def _run_dir(
    runs: Path,
    *,
    pid: int | None = None,
    terminal: str | None = None,
    params: dict | None = None,
    waiting_on: str | None = None,
) -> Path:
    run_dir = runs / "demo-t"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        RunRecord(
            workflow="demo",
            run_id="t",
            started_at="2026-01-01T00:00:00+00:00",
            terminal=terminal,
            pid=_dead_pid() if pid is None else pid,
        ).model_dump_json()
    )
    (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text(
        PyflowCheckpoint(
            state="review",
            flow="Demo",
            workflow="demo",
            inputs={"target": "acme"},
            params={"verdict": {"ok": False}, "budget": 1} if params is None else params,
            waiting_on=waiting_on,
            seq=7,
        ).model_dump_json()
    )
    return run_dir


def _control(runs: Path, *argv: str) -> None:
    cli_main(
        ["control", *argv, "--run", "t", "--runs-dir", str(runs)],
        workflow="demo",
        registry=_REGISTRY,
    )


def _checkpoint(run_dir: Path) -> PyflowCheckpoint:
    return PyflowCheckpoint.model_validate_json(
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text()
    )


# --- rewind ------------------------------------------------------------------------------


def test_rewind_moves_the_checkpoint_carries_params_by_name_and_records_it(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs, waiting_on="questions.md")

        _control(runs, "rewind", "--to", "build", "--param", "item=G2")

        checkpoint = _checkpoint(run_dir)
        # `budget` is a name `build` takes, so it rides along; `verdict` is not, and is
        # dropped and reported rather than failing the edit.
        assert (checkpoint.state, checkpoint.params) == ("build", {"item": "G2", "budget": 1})
        # The gate belonged to the state the run left; re-arming it would park the
        # rewound state on a question it never asked.
        assert checkpoint.waiting_on is None
        backups = list(run_dir.glob("checkpoint.rewound-*.json"))
        assert len(backups) == 1
        assert json.loads(backups[0].read_text())["state"] == "review"
        event = json.loads((run_dir / ArtifactWriter.EVENTS_FILE).read_text().splitlines()[-1])
        assert (event["phase"], event["node"], event["from_state"]) == ("rewind", "build", "review")
        assert event["from_waiting_on"] == "questions.md"
        out = capsys.readouterr().out
        assert "review -> build" in out and "dropped: verdict" in out, out


def test_a_param_can_come_from_a_turn_output_already_on_disk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        (run_dir / "check").mkdir()
        (run_dir / "check" / "output.json").write_text('{"ok": true, "notes": "fine"}')

        _control(runs, "rewind", "--to", "review", "--param-from-turn", "verdict=check")

        assert _checkpoint(run_dir).params == {
            "verdict": {"ok": True, "notes": "fine"},
            "budget": 1,
        }


def test_keep_narrows_what_is_carried() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        _control(runs, "rewind", "--to", "review", "--keep", "verdict")

        assert _checkpoint(run_dir).params == {"verdict": {"ok": False}}


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--to", "nowhere"], "has no state 'nowhere'"),
        (["--to", "build"], "required parameter(s): item"),
        (["--to", "build", "--param", "item=G1", "--param", "budget=lots"], "budget"),
        (["--to", "review", "--keep", "missing"], "--keep names missing"),
    ],
)
def test_a_rewind_the_resume_would_reject_is_refused_and_writes_nothing(
    capsys, argv: list[str], message: str
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        before = (run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text()

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "rewind", *argv)

        assert excinfo.value.code == 1
        assert message in capsys.readouterr().err
        assert (run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text() == before
        assert not list(run_dir.glob("checkpoint.rewound-*.json"))


def test_a_run_whose_pid_is_alive_is_refused(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs, pid=os.getpid())
        before = (run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text()

        with pytest.raises(SystemExit):
            _control(runs, "rewind", "--to", "review")

        assert "is alive" in capsys.readouterr().err
        assert (run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text() == before


def test_a_run_something_is_serving_is_refused_whatever_its_pid_says(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        channel = control.SocketChannel.open(run_dir)
        try:
            with pytest.raises(SystemExit):
                _control(runs, "rewind", "--to", "review")
        finally:
            channel.close()

        assert "control socket" in capsys.readouterr().err


def test_a_finished_run_is_refused_but_a_failed_one_can_be_repaired(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        done = Path(tmp) / "done"
        _run_dir(done, terminal="terminal")
        with pytest.raises(SystemExit):
            _control(done, "rewind", "--to", "review")
        assert "already finished" in capsys.readouterr().err

        failed = Path(tmp) / "failed"
        run_dir = _run_dir(failed, terminal="fail")
        _control(failed, "rewind", "--to", "review")
        assert _checkpoint(run_dir).state == "review"


def test_rewind_flags_are_refused_on_other_verbs(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit):
            _control(runs, "reload", "--to", "review")

        assert "takes no --to" in capsys.readouterr().err


# --- status --params / stop --wait -------------------------------------------------------


def test_status_params_reads_the_checkpoint_without_asking_the_run(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs, waiting_on="questions.md")

        _control(runs, "status", "--params")

        assert json.loads(capsys.readouterr().out) == {
            "state": "review",
            "flow": "Demo",
            "waiting_on": "questions.md",
            "params": {"verdict": {"ok": False}, "budget": 1},
        }


def test_wait_gone_returns_once_the_pid_is_gone_and_fails_while_it_lives(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "gone"
        offline.wait_gone(_run_dir(runs), timeout=1)
        assert "is gone" in capsys.readouterr().out

        alive = Path(tmp) / "alive"
        with pytest.raises(SystemExit):
            offline.wait_gone(_run_dir(alive, pid=os.getpid()), timeout=0.1)
        assert "still alive" in capsys.readouterr().err


# --- resume ------------------------------------------------------------------------------


def test_resume_line_swaps_the_backend_flags_for_the_named_cli() -> None:
    record = LaunchRecord(
        resume_argv=["workhorse-demo", "run", "--profile", "cheap", "--cli=claude", "--auto"]
    )

    assert offline.resume_line(record, "opencode") == [
        "workhorse-demo", "run", "--auto", "--cli", "opencode",
    ]
    assert offline.resume_line(record, "") == list(record.resume_argv)


def _launch(run_dir: Path, argv: list[str], *, container: bool = False) -> None:
    (run_dir / "launch.json").write_text(
        LaunchRecord(resume_argv=argv, cwd=str(run_dir), container=container).model_dump_json()
    )


def test_resume_relaunches_detached_and_returns_once_the_run_serves(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        serve = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
            "from workhorse import control\n"
            f"channel = control.SocketChannel.open({str(run_dir)!r})\n"
            "time.sleep(30)\n"
        )
        _launch(run_dir, [sys.executable, "-c", serve])

        child = offline.run_resume(run_dir, "", timeout=20)
        try:
            out = capsys.readouterr().out
            assert f"resumed {run_dir}: pid {child.pid}" in out and "Demo.review" in out, out
            assert control.listening(run_dir)
        finally:
            child.kill()
            child.wait()


def test_a_resume_that_dies_before_serving_is_an_error_with_its_log(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        _launch(run_dir, [sys.executable, "-c", "print('no such flow'); raise SystemExit(3)"])

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "resume", "--timeout", "20")

        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "exited with 3" in err and "no such flow" in err, err
        assert (run_dir / offline.RESUME_LOG).exists()


@pytest.mark.parametrize(
    ("argv", "container", "message"),
    [
        (["true"], True, "container"),
        ([], False, "no resume line"),
    ],
)
def test_a_launch_record_that_cannot_be_run_here_is_refused(
    capsys, argv: list[str], container: bool, message: str
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        _launch(run_dir, argv, container=container)

        with pytest.raises(SystemExit):
            _control(runs, "resume")

        assert message in capsys.readouterr().err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
