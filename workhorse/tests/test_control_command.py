"""`workhorse-<name> control reload` — the operator's half of a live reload.

The run being reloaded is a different process, usually in a different container, so this
command is exactly three things: work out which run dir is meant, say it on that run's
control socket, and report what the run appeared to be doing. What it must *not* do is
block waiting for the reload to land — the whole point is a one-line nudge that ends,
not a second foreground process to watch.

The tests below pin the halves that fail quietly: the message carries the flags that were
typed (a `--at-boundary` silently dropped would cut a turn the operator asked to let
finish), the run is resolved by every name the operator already has for it, and — the one
the request file could never do — a run nobody is listening for is an error rather than a
message written into a directory and never read.

Run: uv run python tests/test_control_command.py   (or via pytest)
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from workhorse import control  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.cli import control as control_cmd  # noqa: E402
from workhorse.cli import main as cli_main  # noqa: E402
from workhorse.pyflow.registry import Registry  # noqa: E402
from workhorse.records import PyflowCheckpoint, RunRecord  # noqa: E402
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK  # noqa: E402


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


class _Listener:
    """A run that is listening, standing in for the process being reloaded.

    The command talks to a socket now, so a test of it needs something on the other end.
    The reply is served from a thread because the client waits for one on the same
    connection — the same shape the streaming loop has, minus the turn it is cutting.
    """

    def __init__(self, run_dir: Path) -> None:
        self.channel = control.SocketChannel.open(run_dir)
        self.taken: list[control.Request] = []
        #: What this stand-in replies with, when a test needs a particular verdict.
        self.answer: dict[str, object] | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            request = control.wait_until(
                self._stop.is_set,
                timeout=10,
                clock=SYSTEM_CLOCK,
                channel=self.channel,
                tick=0.02,
            )
            if request is None:
                continue
            self.taken.append(request)
            self.channel.reply(
                self.answer
                if self.answer is not None
                else {"ok": True, "cut": request.cuts_the_turn}
            )

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        self.channel.close()


@contextmanager
def _listening(run_dir: Path) -> Iterator[_Listener]:
    listener = _Listener(run_dir)
    try:
        yield listener
    finally:
        listener.close()


def _control(runs: Path, *argv: str) -> None:
    cli_main(["control", *argv], workflow="demo", registry=Registry("demo"))


def test_reload_says_it_on_the_socket_the_run_is_listening_on(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            _control(runs, "reload", "--run", "t", "--runs-dir", str(runs))

        # The default is to cut the turn, because the default reason to reload is that
        # the turn is burning tokens on a flow the operator has already fixed.
        assert [(r.action, r.core, r.at_boundary) for r in listener.taken] == [
            ("reload", False, False)
        ]
        out = capsys.readouterr().out
        # The report is evidence, not confirmation — it says where the run was, so a
        # request that landed on the wrong run is visible immediately.
        assert "Qa.plan_story" in out, out
        assert f"pid {os.getpid()} is alive" in out, out
        assert "'cut': True" in out, out


def test_the_flags_that_were_typed_are_the_flags_that_are_sent() -> None:
    """A dropped `--at-boundary` would cut a turn the operator asked to let land, and a
    dropped `--core` would silently reload half of what was asked for."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            _control(
                runs, "reload", "--run", "t", "--runs-dir", str(runs), "--core", "--at-boundary"
            )

        assert [(r.core, r.at_boundary) for r in listener.taken] == [(True, True)]


def test_a_run_is_found_by_its_id_its_dir_name_or_its_path() -> None:
    """The three spellings an operator already has in their shell history. A name that
    resumes a run has to be a name that can reload it, or the two commands drift."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            for spec in ("t", "demo-t", str(run_dir)):
                _control(runs, "reload", "--run", spec, "--runs-dir", str(runs))

        assert len(listener.taken) == 3, listener.taken


def test_with_no_run_named_the_newest_unfinished_run_is_taken(capsys) -> None:
    """Worth having and worth bounding: the operator watching one run should not have to
    retype an id they never chose, but a finished run must not absorb the request."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        done = _run_dir(runs, "demo-done", terminal="terminal")
        live = _run_dir(runs, "demo-live")

        with _listening(done) as wrong, _listening(live) as right:
            _control(runs, "reload", "--runs-dir", str(runs))

        assert len(right.taken) == 1
        assert wrong.taken == []
        assert str(live) in capsys.readouterr().out


def test_a_run_that_does_not_exist_is_an_error_not_a_new_directory(capsys) -> None:
    """A mistyped path used to be created on the way to writing a request into it, and
    the operator would be left watching a run that never sees it."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "reload", "--run", "typo", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        assert "no run dir for 'typo'" in capsys.readouterr().err
        assert not (runs / "demo-typo").exists()


def test_a_run_nobody_is_listening_for_is_an_error_not_a_reassuring_line(capsys) -> None:
    """The failure the request file could not report. A channel exists only while the run
    does, so nothing listening means nothing will ever act — and saying "reload requested"
    for a run that finished hours ago is the misreport this exit code exists to prevent."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs, "demo-t", terminal="terminal")

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "reload", "--run", "t", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        err = capsys.readouterr().err
        assert "no run is listening" in err, err
        assert "already finished" in err, err


def test_status_is_answered_by_the_run_and_not_by_the_run_dir(capsys) -> None:
    """The one thing the disk cannot say: this process is still serving this run dir.

    A pid in `run.json` and a checkpoint on disk survive the process that wrote them, so
    reading them proves nothing about what is happening now. A reply on the run's own
    socket does, which is why `status` is a message rather than a second reader of the
    same files.
    """
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        control.report_with(lambda: {"attached": True, "state": "plan_story", "flow": "Qa"})
        try:
            with _listening(run_dir) as listener:
                _control(runs, "status", "--run", "t", "--runs-dir", str(runs))
        finally:
            control.report_with(None)

        out = capsys.readouterr().out
        assert "attached: True" in out, out
        assert "state: plan_story" in out, out
        # Answered below the wait, so the run never had to stop what it was doing —
        # the property that makes `status` safe to ask of a run in a six-day cap sleep.
        assert listener.taken == []


def test_a_run_that_never_answered_reports_from_disk_and_says_which_it_is(capsys) -> None:
    # A busy script node reads the channel only between turns, so an unanswered query is
    # normal. What must not happen is it reading as an error, or as an answer.
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        control_cmd._report(run_dir, {})

        out = capsys.readouterr().out
        assert "did not answer" in out, out
        assert "Qa.plan_story" in out, out
        assert f"pid {os.getpid()} is alive" in out, out


def test_a_cli_switch_travels_as_a_core_reload_naming_the_cli(capsys) -> None:
    """`switch-cli` is not a verb on the wire, on purpose. Every waiting site already
    knows how to honour a `--core` reload, and honouring a switch is that plus one
    argument in the argv the new image comes back on — so a verb of its own would need a
    consumer at each of those sites just to mean the same thing."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            _control(runs, "switch-cli", "claude", "--run", "t", "--runs-dir", str(runs))

        assert [(r.action, r.core, r.cli) for r in listener.taken] == [
            ("reload", True, "claude")
        ], listener.taken
        assert "re-enter on claude" in capsys.readouterr().out


def test_a_switch_with_no_cli_and_a_reload_with_one_are_both_refused(capsys) -> None:
    """Both directions, because both are silent otherwise: a switch with nothing to
    switch to would go out as a plain reload, and a name typed after `reload` would be
    dropped — which from the operator's side looks exactly like a switch that worked."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "switch-cli", "--run", "t", "--runs-dir", str(runs))
        assert excinfo.value.code == 1
        assert "needs the name to switch to" in capsys.readouterr().err

        with pytest.raises(SystemExit) as excinfo:
            _control(runs, "reload", "claude", "--run", "t", "--runs-dir", str(runs))
        assert excinfo.value.code == 1
        assert "takes no name" in capsys.readouterr().err


def test_a_profile_switch_is_its_own_verb_carrying_the_name(capsys) -> None:
    """The opposite of `switch-cli`: nothing about it is a reload. The profile is
    re-narrowed every turn, so the run only has to be told a name — no process image, and
    no `--core`. Its own field rather than a second meaning for `cli`, because the two are
    independent axes and the run has to know which was meant."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            _control(runs, "switch-profile", "cheap", "--run", "t", "--runs-dir", str(runs))

        assert [(r.action, r.core, r.cli, r.profile) for r in listener.taken] == [
            ("switch-profile", False, "", "cheap")
        ], listener.taken
        assert "resolve from cheap from the next turn on" in capsys.readouterr().out


def test_a_refused_profile_switch_exits_nonzero(capsys) -> None:
    """The run is what refuses — an unknown profile, or one with no entries for the CLI
    this run drives — and an operator's script must be able to see that."""
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)

        with _listening(run_dir) as listener:
            listener.answer = {"ok": False, "error": "unknown profile 'cheap'"}
            with pytest.raises(SystemExit) as excinfo:
                _control(
                    runs, "switch-profile", "cheap", "--run", "t", "--runs-dir", str(runs)
                )
        assert excinfo.value.code == 1
        assert "unknown profile" in capsys.readouterr().out


if __name__ == "__main__":
    print("run with pytest: uv run python -m pytest tests/test_control_command.py")
