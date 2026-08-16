#!/usr/bin/env python3
"""The failure-notification hook: what it reports, where, and what it refuses to do.

Standalone (`uv run python tests/test_onfail.py`) and pytest-compatible, like every file
here. Nothing spawns a real terminal or a real agent: the spawn path is exercised with
`sh -c` against a temp file, and the tty path against a plain file standing in for a
terminal device — which is exactly what a tty is from the writer's side.
"""

import logging
import os
import pty
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from workhorse.config_run import RunConfig
from workhorse.pyflow import run as run_mod
from workhorse.pyflow.errors import RunBudgetExceeded, WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow
from workhorse.onfail import (
    ON_FAIL_ENV,
    ON_FAIL_PID_ENV,
    Failure,
    notify_failure,
    spawn,
    tty_of,
    write_to_tty,
)

QUIET = logging.getLogger("test.onfail")
QUIET.addHandler(logging.NullHandler())
QUIET.propagate = False


def _failure(**overrides):
    fields = dict(
        run_id="coder-abc123",
        run_dir="/runs/coder-abc123",
        workflow="coder",
        repo="/repo",
        node="qa",
        error="QA never passed for story '02-print' after 3 attempt(s)",
        error_class="WorkflowFailed",
        resume_cmd="workhorse-coder run --resume-run /runs/coder-abc123",
    )
    fields.update(overrides)
    return Failure(**fields)


def test_the_banner_carries_what_the_operator_needs_to_act():
    """It has to be actionable from the terminal alone — the operator is not going to go
    read the run dir to find out which run this even was."""
    banner = _failure().banner()
    for expected in (
        "coder-abc123",
        "qa",
        "WorkflowFailed",
        "02-print",
        "--resume-run /runs/coder-abc123",
    ):
        assert expected in banner, (expected, banner)
    # Bracketed by blank lines: it lands mid-scrollback and has to be findable by eye.
    assert banner.startswith("\n"), repr(banner[:10])
    assert banner.endswith("\n"), repr(banner[-10:])
    print("✓ banner carries run id, node, error class, and the resume command")


def test_an_empty_field_is_omitted_rather_than_labelled_blank():
    """A run that died before any state has no node. `node   ` with nothing after it
    reads as a missing value the notifier failed to fetch, which sends the operator
    looking for a bug that isn't there."""
    banner = _failure(node="", repo="").banner()
    assert "node" not in banner, banner
    assert "repo" not in banner, banner
    assert "coder-abc123" in banner, banner
    print("✓ empty fields are dropped from the banner")


def test_the_hook_environment_carries_the_failure_and_not_the_hook():
    """Every field reaches the child as a variable, and the variable that ARMED the hook
    does not — a hook that starts another run must not arm the same hook again."""
    env = _failure().env()
    assert env["WORKHORSE_RUN_ID"] == "coder-abc123"
    assert env["WORKHORSE_NODE"] == "qa"
    assert env["WORKHORSE_ERROR_CLASS"] == "WorkflowFailed"
    assert env["WORKHORSE_RESUME_CMD"].startswith("workhorse-coder run")
    assert ON_FAIL_ENV not in env, env.get(ON_FAIL_ENV)
    assert ON_FAIL_PID_ENV not in env, env.get(ON_FAIL_PID_ENV)
    print("✓ the failure reaches the child; the arming variables do not")


def test_a_spawned_hook_sees_the_failure_and_does_not_block_the_run():
    """The run is exiting. A hook that took ten seconds would hold the process open for
    ten seconds, so the spawn must return before the child does."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"
        started = time.monotonic()
        assert spawn(
            f'sleep 0.4; printf "%s" "$WORKHORSE_RUN_ID" > {marker}',
            _failure().env(),
            QUIET,
        )
        assert time.monotonic() - started < 0.3, "spawn waited for the child"
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        assert marker.read_text() == "coder-abc123", marker.read_text()
    print("✓ the hook runs detached, with the failure in its environment")


def test_a_broken_hook_is_reported_but_never_raises():
    """A hook that cannot run must not replace the workflow's diagnosis with a diagnosis
    of the hook — the operator would arrive to a message about a missing binary and no
    idea which story broke. A command that fails only once it is RUNNING is invisible
    here by construction: the run is gone by then, which is the whole point."""
    assert spawn("this-command-does-not-exist-8f3a", _failure().env(), QUIET) is True
    assert spawn("\x00 not a command", _failure().env(), QUIET) is False
    print("✓ an unstartable hook returns False instead of raising")


def test_a_missing_repo_does_not_silence_the_notification():
    """The hook starts in the run's repo so an editor opens in the right place — but a
    run whose workspace was deleted (a scratch clone, a torn-down mount) is exactly the
    run that most needs to say so. An unusable directory must degrade, not fail."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"
        assert spawn(f"touch {marker}", _failure(repo="/nonexistent-repo").env(), QUIET)
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        assert marker.exists(), "a missing repo dir swallowed the notification"
    print("✓ a deleted workspace still gets reported")


def test_nothing_configured_is_a_silent_no_op():
    """The overwhelmingly common case: somebody is sitting there watching the run."""
    assert notify_failure(_failure(), QUIET) is False
    assert notify_failure(_failure(), QUIET, command="   ", pid=0) is False
    print("✓ an unconfigured hook does nothing and says so")


def test_the_failure_lands_on_a_named_terminal():
    """The point of --on-fail-pid: a shell the operator already has open, which works the
    same over SSH, where a hook that opens a window has nowhere to open it."""
    parent, child = pty.openpty()
    try:
        # A shell parked on the pty: a real process whose fd 0 IS a terminal, which is
        # what tty_of has to resolve.
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stdin.readline()"],
            stdin=child,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            device = tty_of(proc.pid)
            assert device is not None and device.startswith("/dev/pts/"), device
            assert write_to_tty(proc.pid, _failure().banner(), QUIET) is True
            seen = os.read(parent, 4096).decode()
            assert "WORKHORSE RUN FAILED: coder-abc123" in seen, seen
        finally:
            proc.kill()
            proc.wait(timeout=5)
    finally:
        os.close(parent)
        os.close(child)
    print("✓ the failure is printed on the terminal of a named pid")


def test_a_pid_with_no_terminal_is_a_warning_not_a_crash():
    """Every way this goes wrong is a normal situation: a pid that has since exited, one
    that never had a terminal, one belonging to somebody else."""
    assert write_to_tty(2_147_483_646, "x", QUIET) is False
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.readline()"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert tty_of(proc.pid) is None
        assert write_to_tty(proc.pid, "x", QUIET) is False
    finally:
        proc.kill()
        proc.wait(timeout=5)
    print("✓ a pid with no terminal warns and moves on")


def test_both_channels_are_attempted_independently():
    """An operator who set a pid AND a command asked to be told twice; the terminal
    having gone away is not a reason to skip the webhook."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"
        assert notify_failure(
            _failure(),
            QUIET,
            command=f"touch {marker}",
            pid=2_147_483_646,  # a pid that cannot have a terminal
        ) is True
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        assert marker.exists(), "the command was skipped when the tty write failed"
    print("✓ a dead terminal does not suppress the configured command")


def test_the_config_reads_both_variables():
    """`from_env` is the only place these are read, so this is where the names are
    pinned."""
    config = RunConfig.from_env(
        {ON_FAIL_ENV: "  notify-send hi  ", ON_FAIL_PID_ENV: "4321"}
    )
    assert config.on_fail == "notify-send hi", config.on_fail
    assert config.on_fail_pid == 4321, config.on_fail_pid

    bare = RunConfig.from_env({})
    assert bare.on_fail == ""
    assert bare.on_fail_pid == 0

    # A typo in how a run would have been ANNOUNCED must not refuse to start the run.
    typo = RunConfig.from_env({ON_FAIL_PID_ENV: "-3"})
    assert typo.on_fail_pid == 0, typo.on_fail_pid
    assert RunConfig.from_env({ON_FAIL_PID_ENV: "nonsense"}).on_fail_pid == 0
    print("✓ WORKHORSE_ON_FAIL / _PID are read, trimmed, and degrade to off")


class _Failing(Workflow):
    """A one-state flow whose body never runs — `drive` is substituted below. The
    registry only needs a real class to resolve a directory and instantiate."""

    def start(self) -> Transition:
        return Done(None)


class _TestRegistry(Registry):
    """Prompts resolve to this `tests/` folder; a test module is not a package, so the
    real `directory()` raises for a reason unrelated to what is under test. Same shim as
    test_run_terminal.py and test_run_budget.py."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _registry() -> Registry:
    registry = _TestRegistry("faller")
    registry.add_flows(main=_Failing)
    registry.entry = _Failing
    return registry


#: Built once — `add_flows` refuses a second claim on `_Failing`.
REGISTRY = _registry()


def _drive_a_run_that_dies(tmp: str, exc: BaseException, **config_kwargs) -> int:
    """Drive one transition, then raise `exc` out of the state — the shape of a real
    give-up, at the level where the driver decides whether to announce it."""

    def fake_drive(wf, env, resume=None):
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="_Failing", ctx={})
        raise exc

    with patch.object(run_mod, "drive", fake_drive):
        return run_pyflow(
            RunInvocation(
                registry=REGISTRY,
                runs_dir=Path(tmp) / "runs",
                flow="main",
                run_id="t",
                config=RunConfig(**config_kwargs),
            )
        )


def test_the_driver_announces_a_workflow_that_gave_up():
    """The wiring, end to end: a `WorkflowFailed` out of a state reaches the hook with
    the state it died in and a resume command that names this run."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"
        code = _drive_a_run_that_dies(
            tmp,
            WorkflowFailed("QA never passed for story '02-print'"),
            on_fail=f"printf '%s|%s|%s' "
            f'"$WORKHORSE_NODE" "$WORKHORSE_ERROR_CLASS" "$WORKHORSE_RESUME_CMD" '
            f"> {marker}",
        )
        assert code == 1, code
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        node, error_class, resume_cmd = marker.read_text().split("|")
        assert node == "start", node
        assert error_class == "WorkflowFailed", error_class
        assert resume_cmd.startswith("workhorse-faller run --resume-run "), resume_cmd
        assert "/runs/faller-t" in resume_cmd, resume_cmd
    print("✓ a give-up reaches the hook with its node and resume command")


def test_a_run_budget_stop_is_announced_too():
    """It is a stop a person has to act on, exactly like a give-up — and unlike a
    give-up it leaves no terminal stamp, so it is even easier to miss."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"
        code = _drive_a_run_that_dies(
            tmp,
            RunBudgetExceeded("run exceeded its wall-clock budget"),
            on_fail=f'printf "%s" "$WORKHORSE_ERROR_CLASS" > {marker}',
        )
        assert code == 1, code
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        assert marker.read_text() == "RunBudgetExceeded", marker.read_text()
    print("✓ a wall-clock stop is announced as well")


def test_a_dry_run_check_does_not_wake_anybody():
    """Reaching a fail terminal under --dry-run is a check reporting its result. Waking
    an operator for it teaches them to ignore the channel, which costs the notification
    that mattered."""
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "notified"

        def fake_drive(wf, env, resume=None):
            env.writer.write_state_checkpoint(
                "start", {}, inputs={}, flow="_Failing", ctx={}
            )
            raise WorkflowFailed("the stand-in values walked into the fail terminal")

        with patch.object(run_mod, "drive", fake_drive):
            code = run_pyflow(
                RunInvocation(
                    registry=REGISTRY,
                    runs_dir=Path(tmp) / "runs",
                    flow="main",
                    run_id="dry",
                    dry_run=True,
                    config=RunConfig(on_fail=f"touch {marker}"),
                )
            )
        assert code == 0, code
        time.sleep(0.3)
        assert not marker.exists(), "a dry-run check woke the operator"
    print("✓ a dry-run fail terminal notifies nobody")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"\n✅ {len(tests)} on-fail tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
