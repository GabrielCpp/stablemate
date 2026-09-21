"""`control` — steer or stop a run that is already going."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from workhorse import control, reload
from workhorse.artifacts import ArtifactWriter
from workhorse.cli import offline
from workhorse.cli.target import resolve_target
from workhorse.records import PyflowCheckpoint, parse_checkpoint, parse_run_record

NAME = "control"
HELP = (
    "Control a run in flight (reload, stop, status, questions, answer, switch-cli, "
    "switch-profile) or a stopped one (rewind, resume)"
)

SWITCH_CLI = "switch-cli"
SWITCH_PROFILE = reload.SWITCH_PROFILE
REWIND = "rewind"
RESUME = "resume"

_DEFAULT_WAIT_S = 120.0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=[
            "reload", control.STOP, "status", control.QUESTIONS, control.ANSWER,
            SWITCH_CLI, SWITCH_PROFILE, REWIND, RESUME,
        ],
        help="reload: pick up pushed code and re-enter the checkpoint. status: ask the "
        "run where it is, which is also a proof that this process is the one serving "
        "that run dir. questions: list what the run is blocked asking an operator. "
        "answer: deliver the operator's answer to the gate the run is parked on. "
        "stop: interrupt the run and preserve its checkpoint for resume. "
        "switch-cli: re-enter the same checkpoint on another agent CLI. "
        "switch-profile: resolve the next turn's models from another named profile. "
        "rewind: move a STOPPED run's checkpoint to --to STATE, validated, backed up and "
        "logged. resume: relaunch a stopped run detached from launch.json, optionally on "
        "another agent CLI, and wait until it serves.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        metavar="NAME",
        help="For switch-cli and resume, the agent CLI to come back on (claude, "
        "opencode, …); for switch-profile, the profile to resolve models from next.",
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


    parser.add_argument(
        "--to",
        default=None,
        metavar="STATE",
        help="For rewind: the state the resumed run enters.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="For rewind: set one param of the target state. VALUE is JSON when it "
        "parses as JSON, else the text as typed. Repeatable.",
    )
    parser.add_argument(
        "--param-from-turn",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="For rewind: set one param from a turn's output.json — a node dir, a "
        "turns/<visit> dir or a file, relative to the run dir. Repeatable.",
    )
    parser.add_argument(
        "--keep",
        action="append",
        default=None,
        metavar="NAME",
        help="For rewind: carry only these checkpoint params. Omitted, every param the "
        "target state accepts is carried. Repeatable.",
    )
    parser.add_argument(
        "--params",
        action="store_true",
        help="For status: print the checkpoint's state and params as JSON from disk, "
        "without asking the run — answers for a stopped run too.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="For stop: after the run accepts, block until its pid is gone.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_WAIT_S,
        metavar="S",
        help=f"For stop --wait and resume: seconds to wait (default {_DEFAULT_WAIT_S:g}).",
    )


def run(args: argparse.Namespace) -> None:
    runs_dir = (
        Path(args.runs_dir).resolve()
        if args.runs_dir
        else (Path.cwd() / ".agents" / "runs").resolve()
    )
    run_dir = resolve_target(args.run, runs_dir, args.registry.name)
    _refuse_misplaced_flags(args)
    gate, text = _answer_payload(args)
    if args.action == REWIND:
        if args.target:
            offline.fail(f"rewind takes no name (got {args.target!r}); the state is --to")
        offline.run_rewind(
            run_dir, args.registry, args.to, args.param, args.param_from_turn, args.keep
        )
        return
    if args.action == RESUME:
        offline.run_resume(run_dir, args.target or "", args.timeout)
        return
    if args.action == control.STATUS and args.params:
        offline.print_params(run_dir)
        return
    cli, profile = _switch_target(args.action, args.target)
    if args.action == control.STOP and (args.core or args.at_boundary):
        print("error: stop takes no --core or --at-boundary", file=sys.stderr)
        raise SystemExit(1)
    request = control.Request(
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
    except (OSError, control.ControlProtocolError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"  run:     {_liveness(run_dir)}", file=sys.stderr)
        sys.exit(1)

    if args.action == control.STOP:
        if reply.get("ok") is True and reply.get("action") == control.STOP:
            print(f"stop accepted for {run_dir}")
            if args.wait:
                offline.wait_gone(run_dir, args.timeout)
            return
        reason = reply.get("error") or "the run did not acknowledge stop; its outcome is unconfirmed"
        print(f"error: {reason}", file=sys.stderr)
        raise SystemExit(1)

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


def _refuse_misplaced_flags(args: argparse.Namespace) -> None:
    """A flag typed after the wrong verb is an error, not dropped — for the same reason `_switch_target` refuses a stray name: silence reads as a request that worked."""
    rewind_flags = args.to is not None or args.param or args.param_from_turn or args.keep
    if rewind_flags and args.action != REWIND:
        offline.fail(f"{args.action} takes no --to, --param, --param-from-turn or --keep")
    if args.params and args.action != control.STATUS:
        offline.fail(f"{args.action} takes no --params (it is `status --params`)")
    if (args.core or args.at_boundary) and args.action in (REWIND, RESUME):
        offline.fail(f"{args.action} takes no --core or --at-boundary")
    if args.wait and args.action != control.STOP:
        offline.fail(f"{args.action} takes no --wait (it is `stop --wait`)")


def _switch_target(action: str, name: str | None) -> tuple[str, str]:
    """The (cli, profile) a switch verb named, having rejected the ways of misspelling it."""
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
    """The (gate, text) an `answer` carries — and a refusal of the flags anywhere else."""
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
    """Print what the run said it is blocked asking, or that it said nothing."""
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
    """Print the run's verdict on the answer, and make silence an error."""
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
    """Print what the run said about itself, or say that it did not say anything."""
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
    """What `run.json` and signal 0 together say about the process."""
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
    """The state the run last checkpointed — the thing the reload will re-enter."""
    try:
        checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    except (OSError, ValidationError):
        return "no checkpoint yet"
    if not isinstance(checkpoint, PyflowCheckpoint):
        return "a checkpoint from the retired YAML engine, which cannot be reloaded"
    flow = f"{checkpoint.flow}." if checkpoint.flow else ""
    return f"{flow}{checkpoint.state}"
