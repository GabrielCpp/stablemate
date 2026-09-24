"""`replay`: run one recorded agent turn again, from the tree it started on."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError

from workhorse import gitstate, otel, sessions, turnkey
from workhorse.cli.run import backend_for_profile
from workhorse.config_run import RunConfig
from workhorse.records import TreeStart
from workhorse.rundir import resolve_run_dir
from workhorse.runner.ladder import AgentRunner
from workhorse.runner import transcript
from workhorse.runner.turn_record import TurnRecord, parse_turn_record
from workhorse.runner.usage import TurnUsage

NAME = "replay"
HELP = "Run one recorded agent turn again from the tree it started on, and report its cost"

TURNS_DIR = "turns"
REPLAYS_DIR = "replays"
RECORDED_PROMPT = "prompt.md"
VARIANT_GROWTH = 2


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "turn",
        metavar="TURN",
        help="The visit to replay: a directory name under the run's turns/, "
        "e.g. 000-00023-write-page.",
    )
    parser.add_argument(
        "--run",
        required=True,
        metavar="ID|DIR",
        help="Which run recorded the turn: its --run-id, its run-dir name, or a path.",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Where run dirs live (default: ./.agents/runs, the same default as `run`).",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        metavar="FILE",
        help="Send this prompt instead of the recorded prompt.md, to compare a variant.",
    )
    parser.add_argument(
        "--max-prompt-chars",
        type=int,
        default=None,
        metavar="N",
        help="The largest --prompt variant to send, in characters "
        f"(default: {VARIANT_GROWTH} times the recorded prompt.md).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="How many times to run the turn, each from the recorded start (default: 1).",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="The config profile to run under (default: the one the turn recorded).",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="The shared config file to read profiles from, as for `run`.",
    )
    parser.add_argument(
        "--discard",
        action="store_true",
        help="Overwrite uncommitted changes in the turn's working trees and move their "
        "branches back to the turn's start. Without it, replay refuses a tree that has "
        "uncommitted changes or has moved past that start.",
    )


@dataclass(frozen=True, slots=True)
class Replay:
    """One repeat of a recorded turn: where it wrote, how long it took, what it used."""

    index: int
    directory: Path
    wall_s: float
    usage: TurnUsage


def run(args: argparse.Namespace) -> None:
    runs_dir = (
        Path(args.runs_dir).resolve()
        if args.runs_dir
        else (Path.cwd() / ".agents" / "runs").resolve()
    )
    run_dir = resolve_run_dir(args.run, runs_dir, args.registry.name)
    if run_dir is None:
        _fail(f"no run dir for {args.run!r} under {runs_dir}; pass the run's directory path")
    visit_dir = run_dir / TURNS_DIR / args.turn
    record = _read_record(visit_dir)
    prompt = _read_prompt(visit_dir, args.prompt, args.max_prompt_chars)
    if args.repeat < 1:
        _fail(f"--repeat {args.repeat}: a replay runs the turn at least once")
    _refuse_unsafe(record.start_trees, discard=args.discard)

    profile = args.profile if args.profile is not None else record.profile
    backend = backend_for_profile(args.config, profile.strip(), record.backend or None)
    runner = AgentRunner.from_config(
        replace(RunConfig.from_env(os.environ), backend=backend, profile=profile.strip())
    )

    for _ in range(args.repeat):
        replay = replay_turn(runner, record, prompt, run_dir / REPLAYS_DIR / args.turn)
        print(_summary(replay), flush=True)


def replay_turn(runner: AgentRunner, record: TurnRecord, prompt: str, into: Path) -> Replay:
    """Restore the turn's start, run it once more, and keep what it wrote under ``into``."""
    _restore_start(record.start_trees)
    index = _next_index(into)
    directory = into / str(index)
    directory.mkdir(parents=True)
    reply, wall_s, usage = _run_measured(runner, record, prompt, directory)
    _write_result(directory, reply, wall_s, usage)
    return Replay(index=index, directory=directory, wall_s=wall_s, usage=usage)


def _restore_start(starts: list[TreeStart]) -> None:
    for start in starts:
        if start.head:
            gitstate.restore_tree(start)


def _run_measured(
    runner: AgentRunner, record: TurnRecord, prompt: str, directory: Path
) -> tuple[str, float, TurnUsage]:
    recorder = otel.UsageRecorder()
    previous = otel.install(otel.TelemetryHost(active=recorder))
    transcript.bind(directory)
    _ = turnkey.begin(directory, record.node)
    began = time.monotonic()
    try:
        reply = runner.turn(
            prompt,
            record.node,
            sessions.chain_path(directory, record.node),
            model=record.model,
            timeout=record.silence_budget_s if record.silence_budget_s is not None else math.inf,
            budget_scale=record.timeout_scale,
            base_timeout_s=record.base_timeout_s,
            cwd=record.cwd,
            add_dirs=list(record.add_dirs),
            effort=record.effort,
            agent=record.agent,
        )
    finally:
        wall_s = time.monotonic() - began
        turnkey.clear()
        transcript.unbind()
        _ = otel.install(previous)
    usage = TurnUsage()
    for part in recorder.usages:
        usage = usage.merge(part)
    return reply, wall_s, usage


def _write_result(directory: Path, reply: str, wall_s: float, usage: TurnUsage) -> None:
    _ = (directory / "reply.md").write_text(reply, encoding="utf-8")
    _ = (directory / "usage.json").write_text(
        json.dumps({"wall_s": round(wall_s, 1), **asdict(usage)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _summary(replay: Replay) -> str:
    usage = replay.usage
    cost = "?" if usage.total_cost_usd is None else f"${usage.total_cost_usd:.2f}"
    return (
        f"replay {replay.index}: {replay.wall_s / 60:.1f} min, {cost}, "
        f"input {usage.input_tokens or 0}, cache read {usage.cache_read_input_tokens or 0}, "
        f"generated {usage.generated_tokens or 0}, steps {usage.steps or 0}; "
        f"transcripts in {replay.directory / transcript.TRANSCRIPTS_DIR}"
    )


def _read_record(visit_dir: Path) -> TurnRecord:
    path = visit_dir / "turn.json"
    if not path.is_file():
        _fail(f"{path} does not exist; name a directory under the run's {TURNS_DIR}/ that holds a turn.json")
    try:
        return parse_turn_record(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        _fail(f"{path} is not a turn record: {exc}")


def _read_prompt(visit_dir: Path, override: str | None, max_chars: int | None) -> str:
    recorded = visit_dir / RECORDED_PROMPT
    path = Path(override) if override else recorded
    if not path.is_file():
        _fail(f"{path} does not exist; pass --prompt with the prompt file to send")
    prompt = path.read_text(encoding="utf-8")
    if override:
        _check_budget(path, len(prompt), _variant_budget(recorded, max_chars))
    return prompt


def _variant_budget(recorded: Path, max_chars: int | None) -> tuple[int, str]:
    if max_chars is not None:
        return max_chars, "--max-prompt-chars"
    if not recorded.is_file():
        _fail(f"{recorded} does not exist to size a variant against; pass --max-prompt-chars")
    size = len(recorded.read_text(encoding="utf-8"))
    return VARIANT_GROWTH * size, f"{VARIANT_GROWTH} times the recorded {size}-character prompt"


def _check_budget(path: Path, size: int, budget: tuple[int, str]) -> None:
    limit, source = budget
    if size > limit:
        _fail(
            f"{path} is {size} characters, over the {limit} allowed ({source}). "
            "Trim the variant, or raise the limit with --max-prompt-chars."
        )


def _refuse_unsafe(starts: list[TreeStart], *, discard: bool) -> None:
    if discard:
        return
    for start in starts:
        if not start.head:
            continue
        now = gitstate.observe(start.path)
        if now.dirty:
            _fail(
                f"{start.path} has uncommitted changes, and a replay resets it to the "
                "turn's start. Replay against a copy of the checkout, or pass --discard."
            )
        if now.head != start.head:
            _fail(
                f"{start.path} is at {now.head[:12] or 'no commit'}, not the turn's start "
                f"{start.head[:12]}, and a replay resets its branch to that start, dropping "
                "every commit after it. Replay against a copy of the checkout, or pass --discard."
            )


def _next_index(into: Path) -> int:
    taken = [int(p.name) for p in into.glob("*") if p.name.isdigit()] if into.is_dir() else []
    return max(taken, default=0) + 1


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)
