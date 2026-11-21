"""`environment`: prove that an engine turn loads what a plain session of the same CLI loads."""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from typing import Any, NoReturn
from unittest.mock import patch

from workhorse.cli.run import backend_for_profile
from workhorse.config_run import RunConfig
from workhorse.profile import profile_models, resolve_delegates_for, resolve_power_settings
from workhorse.runner import process
from workhorse.runner.backends import AgentProfile
from workhorse.runner.backends.claude import OUTLIVING_TOOLS
from workhorse.runner.failure import BackendInvocationError

NAME = "environment"
HELP = "Compare what an engine turn loads with what a plain session of the same CLI loads"

PROMPT = "Reply with the single word ok."
LIMIT_S = 180.0
KEYS = ("tools", "skills", "agents", "plugins", "slash_commands", "mcp_servers")

SAME, MISSED, UNAVAILABLE, FAILED = 0, 1, 2, 3


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        default=None,
        help="The config profile whose backend and models the engine turn runs under.",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="The shared config file to read profiles from, as for `run`.",
    )


def _names(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v.get("name", "")) if isinstance(v, dict) else str(v) for v in values]


def compare(
    plain: dict[str, Any],
    engine: dict[str, Any],
    refused: tuple[str, ...],
    delegates: tuple[str, ...],
) -> tuple[list[str], int]:
    """One line per list the two init events carry, and the exit code: 1 when the engine turn misses a name, else 0."""
    lines: list[str] = []
    missed = 0
    for key in KEYS:
        have, got = _names(plain.get(key)), _names(engine.get(key))
        gone = [name for name in have if name not in got]
        extra = [name for name in got if name not in have]
        left = [name for name in gone if not (key == "tools" and name in refused)]
        refusal = [name for name in gone if key == "tools" and name in refused]
        added = [name for name in extra if key == "agents" and name in delegates]
        new = [name for name in extra if name not in added]
        missed += len(left)
        parts = [f"{key}: plain {len(have)}, engine {len(got)}"]
        if not (left or new):
            parts.append("same")
        if left:
            parts.append(f"missing from the engine turn: {', '.join(left)}")
        if new:
            parts.append(f"extra in the engine turn: {', '.join(new)}")
        if refusal:
            parts.append(f"refused by the engine: {', '.join(refusal)}")
        if added:
            parts.append(f"added by the engine: {', '.join(added)}")
        lines.append("; ".join(parts))
    if missed:
        lines.append(f"result: the engine turn misses {missed} names")
        return lines, MISSED
    lines.append("result: the engine turn loads everything the plain session loads")
    return lines, SAME


def _init_event(lines: list[str]) -> dict[str, Any] | None:
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
            return event
    return None


def _plain_init(model: str | None) -> dict[str, Any]:
    """The init event of ``claude -p`` started in the current directory."""
    cmd = ["claude", "-p", PROMPT, "--output-format", "stream-json", "--verbose"]
    if model:
        cmd.extend(["--model", model])
    try:
        done = subprocess.run(
            cmd, capture_output=True, text=True, timeout=LIMIT_S, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        _fail(f"the plain session passed its {int(LIMIT_S)} second limit")
    except OSError as exc:
        _fail(f"the plain session did not start: {exc}")
    init = _init_event(done.stdout.splitlines())
    if init is None:
        _fail(f"the plain session sent no init event (exit {done.returncode})")
    return init


@contextmanager
def _watching(seen: list[str]) -> Iterator[None]:
    """Collect every stream line the engine's turn reads."""
    real: Callable[..., tuple[bool, int]] = process.stream_subprocess

    def tap(cmd: list[str], node_id: str, timeout: float, on_line: Callable[[str], object], **options: Any):
        def read(line: str) -> None:
            seen.append(line)
            on_line(line)

        return real(cmd, node_id, timeout, read, **options)

    with patch.object(process, "stream_subprocess", tap):
        yield


def _fail(message: str) -> NoReturn:
    print(f"environment: {message}", flush=True)
    sys.exit(FAILED)


def run(args: argparse.Namespace) -> None:
    profile = (args.profile or "").strip()
    backend = backend_for_profile(args.config, profile, None)
    if backend.name != "claude":
        print(f"environment: not available for {backend.name}, its CLI reports no load list", flush=True)
        sys.exit(UNAVAILABLE)
    model, effort, _ = resolve_power_settings("low", backend.name, None, profile)
    delegates = resolve_delegates_for(backend.name, profile, subagents=backend.supports_subagents)
    resilience = RunConfig.from_env(os.environ).resilience

    plain = _plain_init(model)
    seen: list[str] = []
    try:
        with _watching(seen), redirect_stdout(io.StringIO()):
            backend.run_turn(
                PROMPT,
                "environment",
                None,
                model,
                timeout=LIMIT_S,
                resilience=resilience,
                cwd=None,
                add_dirs=None,
                effort=effort,
                agent=AgentProfile(name="environment"),
                delegates=delegates,
                models=profile_models(backend.name, profile),
            )
    except BackendInvocationError as exc:
        failure = f": {exc}"
    else:
        failure = ""
    engine = _init_event(seen)
    if engine is None:
        _fail(f"the engine turn sent no init event{failure}")
    lines, code = compare(plain, engine, OUTLIVING_TOOLS, tuple(d.name for d in delegates))
    print("\n".join(lines), flush=True)
    sys.exit(code)
