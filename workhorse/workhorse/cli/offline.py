"""The `control` verbs that act on a run nobody is serving: `rewind` and `resume`.

Every other `control` verb is a message to a live process, and the process decides what
to do with it. These two are the opposite: they edit or relaunch a run dir from outside,
which is only sound while no process holds it. A running driver rewrites the checkpoint
at its next transition, so a rewind under it is lost; a second process resumed beside it
is two drivers writing one run dir. So both begin with the same refusal — a pid that
answers signal 0, or a socket something is listening on — and neither has an override.

`status --params` and `stop --wait` live here too, because they read the same two files
the refusal does and exist for the same repair: stop the run, wait until it is really
gone, look at what it holds, move it, bring it back.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from workhorse import control
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow.registry import Registry
from workhorse.records import (
    LaunchRecord,
    PyflowCheckpoint,
    parse_checkpoint,
    parse_launch_record,
    parse_run_record,
)
from workhorse.rewind import RewindError, rewind

#: Where a relaunched run's stdout and stderr go, beside the run it belongs to.
RESUME_LOG = "resume.log"

#: The flags a `resume NAME` replaces in the recorded resume line. They are one axis
#: (a profile names its own CLI, and `run` refuses both together), so both are dropped.
_BACKEND_FLAGS = ("--cli", "--profile")

_POLL_S = 0.5

#: The `terminal` a failed run carries (`workhorse.pyflow.run`); every other value is a
#: run that finished.
FAILED = "fail"


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def pid_alive(pid: int) -> bool:
    """Signal 0: a process with this pid exists. Another user's process counts."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def refuse_if_running(run_dir: Path, verb: str) -> None:
    """Exit 1 unless `run_dir` is a finished-nothing, served-by-nobody run.

    A run that reached its `Done` is refused too: its driver decided it was over, and a
    new position or a relaunch only makes a finished run look unfinished to everything
    that lists runs. A `fail` terminal is not refused — the driver stamps it on exactly
    the failures an operator fixes and continues from, which is what these verbs are for.
    """
    try:
        record = parse_run_record((run_dir / "run.json").read_text())
    except (OSError, ValidationError):
        fail(f"{verb}: {run_dir} has no readable run.json — nothing says a run started here")
    if record.terminal is not None and record.terminal != FAILED:
        fail(f"{verb}: {run_dir} already finished ({record.terminal})")
    if record.pid is not None and pid_alive(record.pid):
        fail(
            f"{verb}: pid {record.pid} of {run_dir} is alive — stop it first "
            "(`control stop --wait`). If that pid was reused by an unrelated process, "
            "the run is dead and run.json is stale; check `ps -p` before acting."
        )
    if control.listening(run_dir):
        fail(f"{verb}: a process is serving {run_dir}'s control socket — stop it first")


# --- rewind ------------------------------------------------------------------------------


def parse_param(spec: str, flag: str) -> tuple[str, str]:
    name, sep, value = spec.partition("=")
    if not sep or not name.strip():
        fail(f"{flag} wants NAME=VALUE, got {spec!r}")
    return name.strip(), value


def json_or_text(value: str) -> Any:
    """`--param n=3` is the number 3 and `--param item=G1` is the string: JSON first,
    and a value that is not JSON is the text as typed, so a bare word needs no quotes."""
    try:
        return json.loads(value)
    except ValueError:
        return value


def turn_output(run_dir: Path, ref: str) -> Any:
    """The `output.json` named by `ref`: a node dir (its latest visit), a `turns/<visit>`
    dir, or a file — each relative to the run dir, or absolute.

    This is how a rewind hands a state the answer a previous turn already gave, instead
    of the operator retyping JSON that is sitting on disk.
    """
    path = Path(ref) if Path(ref).is_absolute() else run_dir / ref
    if path.is_dir():
        path = path / "output.json"
    try:
        return json.loads(path.read_text())
    except OSError as exc:
        fail(f"--param-from-turn: cannot read {path}: {exc}")
    except ValueError as exc:
        fail(f"--param-from-turn: {path} is not JSON: {exc}")


def run_rewind(
    run_dir: Path,
    registry: Registry,
    to_state: str | None,
    params: list[str],
    from_turns: list[str],
    keep: list[str] | None,
) -> None:
    if not to_state:
        fail("rewind needs the state to move to: `control rewind --to STATE`")
    refuse_if_running(run_dir, "rewind")
    set_params: dict[str, Any] = {}
    for spec in params:
        name, value = parse_param(spec, "--param")
        set_params[name] = json_or_text(value)
    for spec in from_turns:
        name, ref = parse_param(spec, "--param-from-turn")
        set_params[name] = turn_output(run_dir, ref)
    try:
        moved = rewind(run_dir, registry, to_state, set_params=set_params, keep=keep)
    except RewindError as exc:
        fail(f"rewind refused, checkpoint unchanged: {exc}")
    print(f"rewound {run_dir}: {moved.from_state} -> {moved.to_state}")
    print(f"  params:  {json.dumps(moved.params, sort_keys=True)}")
    if moved.dropped:
        print(f"  dropped: {', '.join(moved.dropped)}")
    print(f"  backup:  {moved.backup}")
    print("  resume:  control resume [CLI]")


# --- resume ------------------------------------------------------------------------------


def resume_line(record: LaunchRecord, cli: str) -> list[str]:
    """The recorded resume argv, with the backend flags swapped for `--cli CLI`."""
    if not cli:
        return list(record.resume_argv)
    argv: list[str] = []
    skip = False
    for token in record.resume_argv:
        if skip:
            skip = False
            continue
        if token in _BACKEND_FLAGS:
            skip = True
            continue
        if any(token.startswith(f"{flag}=") for flag in _BACKEND_FLAGS):
            continue
        argv.append(token)
    return [*argv, "--cli", cli]


def _tail(path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


def run_resume(run_dir: Path, cli: str, timeout: float) -> subprocess.Popen[bytes]:
    """Relaunch `run_dir` detached from its recorded resume line, and wait until it serves.

    Detached is the point: the relaunched run must outlive this command and the shell
    that typed it, which is what a hand-rolled `nohup … &` gets wrong often enough to be
    worth not typing. Waiting for the socket is the other half — a resume line that dies
    in its first second (a bad `--cli`, a checkpoint the flow rejects) is reported here,
    with its log, instead of being discovered an hour later as a run that never came back.

    Returns the child so a caller that outlives this command can reap it; the CLI does
    not, because it exits and the child is in its own session.
    """
    refuse_if_running(run_dir, "resume")
    try:
        record = parse_launch_record((run_dir / "launch.json").read_text())
    except (OSError, ValidationError) as exc:
        fail(f"resume: no usable launch.json in {run_dir} ({exc}) — run "
             f"`<workflow> run --resume-run {run_dir}` by hand")
    if record.container:
        fail("resume: launch.json holds container coordinates; resume it inside the "
             "container it ran in")
    if not record.resume_argv:
        fail(f"resume: launch.json in {run_dir} records no resume line")
    argv = resume_line(record, cli)
    cwd = record.cwd or str(Path.cwd())
    log_path = run_dir / RESUME_LOG
    with log_path.open("ab") as log:
        log.write(f"\n--- control resume: {' '.join(argv)} (cwd {cwd})\n".encode())
        log.flush()
        try:
            child = subprocess.Popen(
                argv,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            fail(f"resume: cannot launch {argv[0]!r} from {cwd}: {exc}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            print(f"error: resumed run exited with {child.returncode} before serving "
                  f"its control socket. Last lines of {log_path}:", file=sys.stderr)
            print(_tail(log_path), file=sys.stderr)
            raise SystemExit(1)
        if control.listening(run_dir):
            print(f"resumed {run_dir}: pid {child.pid}, serving at {position(run_dir)}")
            print(f"  argv:    {' '.join(argv)}")
            print(f"  log:     {log_path}")
            return child
        time.sleep(_POLL_S)
    print(f"resume launched pid {child.pid} but {run_dir} was not serving after "
          f"{timeout:g}s; it may still be starting. Log: {log_path}")
    return child


# --- status --params / stop --wait -----------------------------------------------------


def position(run_dir: Path) -> str:
    try:
        checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    except (OSError, ValidationError):
        return "no checkpoint yet"
    if not isinstance(checkpoint, PyflowCheckpoint):
        return "a checkpoint from the retired YAML engine"
    return f"{checkpoint.flow}.{checkpoint.state}" if checkpoint.flow else checkpoint.state


def print_params(run_dir: Path) -> None:
    """The checkpoint's state and params as JSON, read from disk — so it answers the same
    for a live run, a stopped one, and one whose process is busy in a script node."""
    path = run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = parse_checkpoint(path.read_text())
    except (OSError, ValidationError) as exc:
        fail(f"cannot read checkpoint {path}: {exc}")
    if not isinstance(checkpoint, PyflowCheckpoint):
        fail(f"{path} is a checkpoint from the retired YAML engine")
    print(json.dumps(
        {
            "state": checkpoint.state,
            "flow": checkpoint.flow,
            "waiting_on": checkpoint.waiting_on,
            "params": checkpoint.params,
        },
        indent=2,
        sort_keys=True,
    ))


def wait_gone(run_dir: Path, timeout: float) -> None:
    """Block until the pid `run.json` records is gone; exit 1 when it outlives `timeout`.

    An acknowledged stop is the run agreeing to stop at its next slice, not having
    stopped — and the next step of every repair (rewind, resume) refuses while the pid
    lives. This is the wait between the two, so it is not a `sleep` someone guesses.
    """
    try:
        pid = parse_run_record((run_dir / "run.json").read_text()).pid
    except (OSError, ValidationError):
        pid = None
    if pid is None:
        print("  (run.json records no pid to wait on)")
        return
    deadline = time.monotonic() + timeout
    while pid_alive(pid):
        if time.monotonic() >= deadline:
            fail(f"pid {pid} is still alive after {timeout:g}s")
        time.sleep(_POLL_S)
    print(f"  pid {pid} is gone; checkpoint at {position(run_dir)}")


__all__ = [
    "RESUME_LOG",
    "print_params",
    "refuse_if_running",
    "resume_line",
    "run_resume",
    "run_rewind",
    "wait_gone",
]
