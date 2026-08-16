"""`control` — say something to a run that is already going, without stopping it.

`reload` asks a live run to cut whatever it is doing, pick the pushed code up, and
re-enter its own checkpoint — the operator's half of :mod:`workhorse.reload`. `switch-cli`
is that same reload carrying the one thing a checkpoint cannot hold: the agent CLI to come
back on, which is chosen at the process edge from `--cli` rather than by the run.
`switch-profile` is the other axis and, unlike the CLI, needs no reload at all: the profile
is re-read and re-narrowed on every turn, so the run only has to be told a new name and the
next turn resolves from it. `status`
asks where it is, and is answered by the run itself: everything in the answer is also on
disk, but a reply *on that run's socket* is the one thing the disk cannot prove — that
this process is the one still serving this run dir. The run is a different process (often
in a different container), so the whole command is: resolve which run dir is meant, say it
on the run's control socket, and report what the run appeared to be doing when it was
asked.

It is deliberately **not** a wait for the *reload*. The run acknowledges the message on
the same connection, which is quick and worth having — a request nobody was listening for
used to look identical to one that landed — but the cut itself happens on the run's own
next select slice. Blocking until then would turn an operator's one-line nudge into a
foreground process they now have to babysit, which is the thing they were reloading to
stop doing. So what this prints past the acknowledgement is evidence rather than
confirmation: the pid, whether it answers signal 0, and the state the last checkpoint
named.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from workhorse import control, reload
from workhorse.artifacts import ArtifactWriter
from workhorse.records import PyflowCheckpoint, parse_checkpoint, parse_run_record
from workhorse.rundir import find_latest_resumable, resolve_run_dir

NAME = "control"
HELP = "Signal a run in flight (reload, status, switch-cli, switch-profile)"

SWITCH_CLI = "switch-cli"
SWITCH_PROFILE = reload.SWITCH_PROFILE


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=["reload", "status", SWITCH_CLI, SWITCH_PROFILE],
        help="reload: pick up pushed code and re-enter the checkpoint. status: ask the "
        "run where it is, which is also a proof that this process is the one serving "
        "that run dir. switch-cli: re-enter the same checkpoint on another agent CLI. "
        "switch-profile: resolve the next turn's models from another named profile.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        metavar="NAME",
        help="For switch-cli, the agent CLI to come back on (claude, opencode, …); for "
        "switch-profile, the profile to resolve models from next.",
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
    cli, profile = _switch_target(args.action, args.target)
    request = control.Request(
        # A CLI switch is a reload on the wire, and deliberately not a verb of its own:
        # honouring it is already what a `--core` reload does — replace the process image
        # and resume the checkpoint — with one more argument in the argv it comes back on.
        # A separate verb would need its own consumer at every waiting site to mean the
        # same thing.
        action=reload.ACTION if cli else args.action,
        core=args.core or bool(cli),
        at_boundary=args.at_boundary,
        cli=cli,
        profile=profile,
    )
    try:
        reply = control.send(run_dir, request)
    except (OSError, FileNotFoundError) as exc:
        # The honest failure, and the one the request file could never report: a channel
        # exists only while the run does, so nobody listening means nobody will act. Exit
        # nonzero rather than printing a reassuring line about a message that went nowhere.
        print(f"error: {exc}", file=sys.stderr)
        print(f"  run:     {_liveness(run_dir)}", file=sys.stderr)
        sys.exit(1)

    if args.action == control.STATUS:
        _report(run_dir, reply)
        return

    if profile:
        # No `when`: a profile switch is only ever honoured at the next state boundary,
        # whatever `--at-boundary` says, and the reply is the run's verdict rather than an
        # acknowledgement — it is the frame that applied it that says whether it could be.
        print(f"profile switch requested for {run_dir}: resolve from {profile} "
              "from the next turn on")
        print(f"  reply:   {reply or 'delivered, no answer'}")
        print(f"  run:     {_liveness(run_dir)}")
        print(f"  at:      {_position(run_dir)}")
        if isinstance(reply, dict) and reply.get("ok") is False:
            sys.exit(1)
        return

    when = "at the next state boundary" if args.at_boundary else "cutting the current turn"
    if cli:
        print(f"switch requested for {run_dir}: re-enter on {cli}, {when}")
    else:
        scope = "workhorse and the workflow" if args.core else "the workflow package"
        print(f"reload requested for {run_dir}: reload {scope}, {when}")
    print(f"  reply:   {reply or 'delivered, no answer'}")
    print(f"  run:     {_liveness(run_dir)}")
    print(f"  at:      {_position(run_dir)}")


def _switch_target(action: str, name: str | None) -> tuple[str, str]:
    """The (cli, profile) a switch verb named, having rejected the ways of misspelling it.

    Both directions are errors rather than tolerated: a switch with no name has nothing to
    switch to, and a name handed to `reload` or `status` would be silently dropped — which
    reads, from the operator's side, exactly like a switch that worked.

    Two fields rather than one string because the two are independent axes, and the run has
    to be told which was meant: a CLI switch costs a process image, a profile switch costs
    nothing but the next turn's resolution.
    """
    if action not in (SWITCH_CLI, SWITCH_PROFILE):
        if name:
            print(f"error: {action} takes no name (got {name!r})", file=sys.stderr)
            sys.exit(1)
        return "", ""
    if not name:
        example = "claude" if action == SWITCH_CLI else "cheap"
        print(f"error: {action} needs the name to switch to, e.g. "
              f"`control {action} {example}`", file=sys.stderr)
        sys.exit(1)
    return (name, "") if action == SWITCH_CLI else ("", name)


def _report(run_dir: Path, reply: dict[str, object]) -> None:
    """Print what the run said about itself, or say that it did not say anything.

    An empty reply is not an error and not silence: the connection was accepted, so the
    process is there — it just is not currently looking at the channel, which is what a
    script node with no wait in it looks like from outside. So the on-disk answer is
    printed underneath either way, and the difference between the two is stated rather
    than smoothed over, because it is the difference between 'busy' and 'wedged'.
    """
    if reply:
        print(f"status of {run_dir}:")
        for key in sorted(reply):
            print(f"  {key}: {reply[key]}")
        return
    print(f"status of {run_dir}: the run did not answer within the timeout")
    print("  (a node that is not waiting on anything reads the channel only between turns)")
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
