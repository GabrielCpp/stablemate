"""`control` — say something to a run that is already going, without stopping it.

Today it has one verb. `reload` asks a live run to cut whatever it is doing, pick the
pushed code up, and re-enter its own checkpoint — the operator's half of
:mod:`workhorse.reload`. The run is a different process (often in a different container),
so the whole command is: resolve which run dir is meant, write the request file
atomically, and report what the run appeared to be doing when it was asked.

It is deliberately **not** a wait. A turn that has been streaming for two hours is cut
within the second, but "cut" is the run's own next select slice, and blocking here to
watch for it would turn an operator's one-line nudge into a foreground process they now
have to babysit — the thing they were reloading to stop doing. What this prints is
therefore evidence, not confirmation: the pid, whether it answers signal 0, and the state
the last checkpoint named.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from workhorse import reload
from workhorse.artifacts import ArtifactWriter
from workhorse.records import PyflowCheckpoint, parse_checkpoint, parse_run_record
from workhorse.rundir import find_latest_resumable, resolve_run_dir

NAME = "control"
HELP = "Signal a run that is already in flight (reload)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=["reload"],
        help="What to ask the run to do. Only 'reload' exists so far.",
    )
    parser.add_argument(
        "--run",
        default=None,
        metavar="ID|DIR",
        help="Which run: its --run-id, its run-dir name, or a path. Defaults to the "
        "most recent run under --runs-dir that has not finished.",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Where run dirs live (default: ./.agents/runs, the same default as `run`).",
    )
    parser.add_argument(
        "--core",
        action="store_true",
        help="Also replace workhorse itself, which costs a process image (the workflow "
        "package alone needs no restart). Names the cost rather than hiding it.",
    )
    parser.add_argument(
        "--at-boundary",
        action="store_true",
        help="Let the streaming turn finish and reload at the next state entry. The "
        "default is to cut the turn, because the default reason to reload is that it "
        "is burning tokens on a flow you have already fixed.",
    )


def run(args: argparse.Namespace) -> None:
    runs_dir = (
        Path(args.runs_dir).resolve()
        if args.runs_dir
        else (Path.cwd() / ".agents" / "runs").resolve()
    )
    run_dir = _target(args.run, runs_dir, args.registry.name)
    path = reload.request(run_dir, core=args.core, at_boundary=args.at_boundary)

    scope = "workhorse and the workflow" if args.core else "the workflow package"
    when = "at the next state boundary" if args.at_boundary else "cutting the current turn"
    print(f"reload requested for {run_dir}: reload {scope}, {when}")
    print(f"  request: {path}")
    print(f"  run:     {_liveness(run_dir)}")
    print(f"  at:      {_position(run_dir)}")


def _target(spec: str | None, runs_dir: Path, workflow_name: str) -> Path:
    """The run dir to write into — named, or the one unfinished run there is.

    Defaulting is worth having and worth bounding: an operator reloading the run they
    are watching should not have to retype an id they never chose, but a *wrong* guess
    would send the request to a run nobody asked about. So the default is the same
    "newest run that never reached a terminal" that `--resume-latest` means, and it is
    printed back, since a reload is only cheap when it lands on the intended run.
    """
    if spec is not None:
        resolved = resolve_run_dir(spec, runs_dir, workflow_name)
        if resolved is None:
            print(
                f"error: no run dir for {spec!r} (looked under {runs_dir})",
                file=sys.stderr,
            )
            sys.exit(1)
        return resolved

    latest = find_latest_resumable(runs_dir)
    if latest is None:
        print(
            f"error: no unfinished run found under {runs_dir} — name one with --run",
            file=sys.stderr,
        )
        sys.exit(1)
    return latest


def _liveness(run_dir: Path) -> str:
    """What `run.json` and signal 0 together say about the process.

    Signal 0 is a permission check, not a delivery: it proves a process with that pid
    exists and is ours to signal. It cannot prove it is *this* run — a pid is reused —
    which is why this is reported rather than acted on. A dead pid is still worth
    writing the request for: the run dir is resumable, and the request is read on entry.
    """
    try:
        record = parse_run_record((run_dir / "run.json").read_text())
    except (OSError, ValidationError):
        return "no run.json — nothing here says a run ever started"
    if record.terminal is not None:
        return f"already finished ({record.terminal}) — the request will not be read"
    if record.pid is None:
        return "in flight, pid not recorded"
    try:
        os.kill(record.pid, 0)
    except ProcessLookupError:
        return f"pid {record.pid} is gone — resume the run and it reloads on entry"
    except PermissionError:
        return f"pid {record.pid} is alive (owned by another user)"
    except OSError as exc:
        return f"pid {record.pid}: {exc}"
    return f"pid {record.pid} is alive"


def _position(run_dir: Path) -> str:
    """The state the run last checkpointed — the thing the reload will re-enter.

    Read from the checkpoint rather than from telemetry so it answers with the collector
    down, which is one of the states an operator reloads *from*.
    """
    try:
        checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    except (OSError, ValidationError):
        return "no checkpoint yet"
    if not isinstance(checkpoint, PyflowCheckpoint):
        return "a checkpoint from the retired YAML engine, which cannot be reloaded"
    flow = f"{checkpoint.flow}." if checkpoint.flow else ""
    return f"{flow}{checkpoint.state}"
