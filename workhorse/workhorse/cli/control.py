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
this process is the one still serving this run dir. `questions` asks what the run is
blocked asking an operator — answered in-band under every wait, like `status` — and
`answer` delivers the operator's reply to the gate the run is parked on: the run writes
it into the gate file itself, so disk keeps the record while the socket carries the
exchange. The run is a different process (often
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
from workhorse.cli.target import resolve_target
from workhorse.records import PyflowCheckpoint, parse_checkpoint, parse_run_record

NAME = "control"
HELP = "Signal a run in flight (reload, status, questions, answer, switch-cli, switch-profile)"

SWITCH_CLI = "switch-cli"
SWITCH_PROFILE = reload.SWITCH_PROFILE


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=["reload", "status", control.QUESTIONS, control.ANSWER, SWITCH_CLI, SWITCH_PROFILE],
        help="reload: pick up pushed code and re-enter the checkpoint. status: ask the "
        "run where it is, which is also a proof that this process is the one serving "
        "that run dir. questions: list what the run is blocked asking an operator. "
        "answer: deliver the operator's answer to the gate the run is parked on. "
        "switch-cli: re-enter the same checkpoint on another agent CLI. "
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
        "--gate",
        default=None,
        metavar="PATH",
        help="For answer: the gate file the answer is for, as an absolute path the run "
        "knows it by. Omitted, the answer lands on whichever gate the run is waiting "
        "on — the run replies with its path either way.",
    )
    parser.add_argument(
        "--text",
        default=None,
        metavar="TXT",
        help="For answer: the operator's answer text. Omit it to read the text from "
        "stdin, which is where a multi-line answer already is.",
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
    run_dir = resolve_target(args.run, runs_dir, args.registry.name)
    cli, profile = _switch_target(args.action, args.target)
    gate, text = _answer_payload(args)
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
        path=gate,
        body=text,
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

    if args.action == control.QUESTIONS:
        _report_questions(run_dir, reply)
        return

    if args.action == control.ANSWER:
        _report_answer(run_dir, reply)
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


def _answer_payload(args: argparse.Namespace) -> tuple[str, str]:
    """The (gate, text) an `answer` carries — and a refusal of the flags anywhere else.

    A `--text` typed after `reload` would be silently dropped, which from the operator's
    side reads exactly like an answer that landed. The text itself may come from stdin —
    that is where a multi-line answer already is — but only when stdin is not a terminal,
    because blocking an interactive shell on a read nobody was told about is a hang, not
    a prompt.
    """
    if args.action != control.ANSWER:
        if args.gate is not None or args.text is not None:
            print(f"error: {args.action} takes no --gate or --text", file=sys.stderr)
            sys.exit(1)
        return "", ""
    if args.text is not None:
        return args.gate or "", args.text
    if sys.stdin.isatty():
        print(
            "error: answer needs the text — --text TXT, or pipe it on stdin",
            file=sys.stderr,
        )
        sys.exit(1)
    return args.gate or "", sys.stdin.read()


def _report_questions(run_dir: Path, reply: dict[str, object]) -> None:
    """Print what the run said it is blocked asking, or that it said nothing.

    An empty reply means the query was never read — a busy script node looks at the
    channel only between turns — which is different from the well-formed "no questions"
    answer a working run gives, and the two must not print alike: one says "ask again",
    the other says "nothing to answer".
    """
    if not reply:
        print(f"questions of {run_dir}: the run did not answer within the timeout")
        print("  (a node that is not waiting on anything reads the channel only between turns)")
        print(f"  run:     {_liveness(run_dir)}")
        print(f"  at:      {_position(run_dir)}")
        return
    if reply.get("ok") is not True:
        print(f"error: {reply.get('error', reply)}", file=sys.stderr)
        sys.exit(1)
    questions = reply.get("questions")
    entries = [q for q in questions if isinstance(q, dict)] if isinstance(questions, list) else []
    if not entries:
        print(f"{run_dir} is not blocked on an operator gate right now")
        return
    print(f"{run_dir} is waiting on an operator:")
    for entry in entries:
        print(f"  gate:    {entry.get('path', '')}")
        print(f"  kind:    {entry.get('kind', '')}")
        print(f"  since:   {entry.get('since', '')}")
        question = str(entry.get("question", "")).strip()
        for line in question.splitlines():
            print(f"    {line}")


def _report_answer(run_dir: Path, reply: dict[str, object]) -> None:
    """Print the run's verdict on the answer, and make silence an error.

    An answer is the one verb where "delivered, no reply" is not good enough: the run
    persists the answer into the gate file *before* acknowledging, so no acknowledgement
    means nothing was written — and an operator told otherwise would walk away from a run
    still parked on the question they believe they answered.
    """
    if not reply:
        print(
            f"error: {run_dir} did not confirm the answer within the timeout — "
            "nothing was written into the gate",
            file=sys.stderr,
        )
        print(f"  run:     {_liveness(run_dir)}", file=sys.stderr)
        print(f"  at:      {_position(run_dir)}", file=sys.stderr)
        sys.exit(1)
    if reply.get("ok") is True:
        print(f"answer delivered to {run_dir}: the run wrote it into {reply.get('path', '')}")
        return
    print(f"error: {reply.get('error', reply)}", file=sys.stderr)
    sys.exit(1)


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
