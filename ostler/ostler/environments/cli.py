"""The `ostler env` argument parser and its dispatch."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from ostler.environments import commands
from ostler.environments.render import SHARED
from ostler.qa import addresses


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    env = sub.add_parser(
        "env", help="bring up a local copy of the stack the books' stack.yml files declare")
    ops = env.add_subparsers(dest="env_op", required=True)

    def copy_flag(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--copy", default="", metavar="NAME",
            help=f"which copy: a run's own one, or `{SHARED}` "
                 f"(default: ${addresses.LEASE_ENV}, else `{SHARED}`)")

    up = ops.add_parser("up", help="bring the targets and everything they need up")
    up.add_argument("targets", nargs="*", metavar="TARGET",
                    help="a book, or one `book:service` (default: the book you stand in)")
    copy_flag(up)
    up.add_argument("--fixtures", default="", metavar="SET[,SET]",
                    help="the fixture sets to load (default: each book's default-fixtures)")
    up.add_argument("--fresh", action="store_true",
                    help="drop the copy's data first, so its fixtures load again")
    up.add_argument("--wait", type=int, default=commands.DEFAULT_WAIT_SECONDS, metavar="SECONDS",
                    help="how long to wait for every service to be ready")
    up.add_argument("--json", action="store_true")

    down = ops.add_parser("down", help="stop a copy and delete its secrets, data and rendered files")
    copy_flag(down)
    down.add_argument("--keep-data", action="store_true",
                      help="keep the copy's volumes and files, so a later `down` drops them")
    down.add_argument("--json", action="store_true")

    ls = ops.add_parser("ls", help="list this stack's copies on this machine")
    ls.add_argument("--json", action="store_true")

    render = ops.add_parser("render", help="write the copy's compose file without starting it")
    render.add_argument("targets", nargs="*", metavar="TARGET")
    copy_flag(render)
    render.add_argument("--fixtures", default="", metavar="SET[,SET]")
    render.add_argument("--json", action="store_true")

    address = ops.add_parser("address", help="print the URL a copy publishes a name at")
    address.add_argument("name", metavar="NAME")
    copy_flag(address)
    address.add_argument("--json", action="store_true")

    check = ops.add_parser("check", help="check that every book's stack.yml fits together")
    check.add_argument("--json", action="store_true")

    compose = ops.add_parser(
        "compose", help="run docker compose against a copy: `ostler env compose -- logs`")
    copy_flag(compose)
    compose.add_argument("compose_args", nargs=argparse.REMAINDER, metavar="-- ARGS")


def run(args: argparse.Namespace, root: Path) -> int:
    copy_name = getattr(args, "copy", "") or os.environ.get(addresses.LEASE_ENV, "") or SHARED
    fixtures = [item for item in getattr(args, "fixtures", "").split(",") if item]
    op = args.env_op
    if op == "compose":
        rest = args.compose_args[1:] if args.compose_args[:1] == ["--"] else args.compose_args
        argv = commands.compose_argv(root, rest, copy_name=copy_name)
        if isinstance(argv, commands.EnvOutcome):
            print(argv.message, file=sys.stderr)
            return 1
        return subprocess.run(argv, check=False).returncode
    if op == "up":
        outcome = commands.cmd_up(root, args.targets, copy_name=copy_name, fixtures=fixtures,
                                  fresh=args.fresh, wait_seconds=args.wait)
    elif op == "down":
        outcome = commands.cmd_down(root, copy_name=copy_name, keep_data=args.keep_data)
    elif op == "ls":
        outcome = commands.cmd_ls(root)
    elif op == "render":
        outcome = commands.cmd_render(root, args.targets, copy_name=copy_name, fixtures=fixtures)
    elif op == "address":
        outcome = commands.cmd_address(root, args.name, copy_name=copy_name)
    else:
        outcome = commands.cmd_check(root)
    if args.json:
        print(json.dumps(outcome.data, indent=2))
    else:
        print(outcome.message, file=sys.stdout if outcome.ok else sys.stderr)
    return 0 if outcome.ok else 1
