"""The `paddock` command line."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from paddock import loader, paths, sandbox
from paddock.homeconfig import HomeConfigError
from paddock.registry import TaskError
from paddock.runner import RunError, execute
from paddock.sandbox import Sandbox, SandboxError

logger = logging.getLogger("paddock")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paddock", description="Run a benchmark task.")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a benchmark's task end to end")
    run.add_argument("benchmark")
    run.add_argument("task")
    run.add_argument(
        "--no-pin-project",
        action="store_true",
        help="drive the checkout in place instead of a clone pinned at its HEAD",
    )
    run.add_argument(
        "--quiet",
        action="store_true",
        help="do not tee each command's output to stderr as it is written",
    )
    run.set_defaults(handler=cmd_run)

    listing = sub.add_parser("list", help="the benchmarks under the benchmark root and their tasks")
    listing.set_defaults(handler=cmd_list)

    _add_sandbox_commands(
        sub.add_parser("sandbox", help="run a command where stablemate is installed as packages and its checkout is absent")
    )
    return parser


def _add_sandbox_commands(parser: argparse.ArgumentParser) -> None:
    sandbox_commands = parser.add_subparsers(dest="sandbox_command", required=True)

    sandbox_build = sandbox_commands.add_parser("build", help="build the sandbox image from this checkout's packages")
    sandbox_build.add_argument("--tag", default=sandbox.IMAGE)
    sandbox_build.add_argument(
        "--claude-code-version", default="", help="the Claude Code release to install; default: this machine's"
    )
    sandbox_build.add_argument(
        "--opencode-version", default="", help="the opencode release to install; default: this machine's"
    )
    sandbox_build.set_defaults(handler=cmd_sandbox_build)

    sandbox_run = sandbox_commands.add_parser(
        "run",
        help="run a command in the app, inside the sandbox",
        description=(
            f"The app is mounted at {sandbox.WORK}/<its directory name> and is the working directory, "
            + f"--runs-dir at {sandbox.RUNS}, and --config at {sandbox.CONFIG}. "
            + f"The home skill folders that exist are mounted read-only under {sandbox.HOME}. Nothing else of this machine is visible."
        ),
    )
    sandbox_run.add_argument("--app", type=Path, required=True, help="the repo the command works on")
    sandbox_run.add_argument("--runs-dir", type=Path, required=True, help="where the command writes its runs")
    sandbox_run.add_argument("--config", type=Path, required=True, help="the stablemate config the command reads")
    sandbox_run.add_argument(
        "--credentials",
        type=Path,
        default=Path.home() / ".claude" / ".credentials.json",
        help="the Claude Code login, mounted when the config runs claude",
    )
    sandbox_run.add_argument(
        "--opencode-auth",
        type=Path,
        default=Path.home() / ".local" / "share" / "opencode" / "auth.json",
        help="the opencode login, mounted when the config runs opencode",
    )
    sandbox_run.add_argument(
        "--base-library",
        type=Path,
        help=(
            f"a base library to render the app's skills from, mounted read-only at {sandbox.BASE_LIBRARY}. "
            + "Left out, farrier fetches the published one, as it would on a client's machine"
        ),
    )
    sandbox_run.add_argument("--image", default=sandbox.IMAGE)
    sandbox_run.add_argument("--name", default="", help="the container's name, to stop it with `docker stop`")
    sandbox_run.add_argument("command", nargs=argparse.REMAINDER, help="after `--`, the command to run")
    sandbox_run.set_defaults(handler=cmd_sandbox_run)


def cmd_run(args: argparse.Namespace) -> int:
    root = paths.root()
    benchmark, task = loader.load_task(root, args.benchmark, args.task)
    result = execute(
        benchmark,
        task,
        root=root,
        pin_project=not args.no_pin_project,
        echo=not args.quiet,
    )
    for outcome in result.outcomes:
        mark = {"ok": "ok  ", "failed": "FAIL", "skipped": "skip"}[outcome.status]
        print(f"{mark} {outcome.name}  {outcome.seconds:.1f}s{'  ' + outcome.error if outcome.error else ''}")
    if result.score is not None:
        print(result.score.render())
    print(f"run     {result.name}")
    print(f"result  {result.result}")
    return 0 if result.ok else 1


def cmd_list(args: argparse.Namespace) -> int:
    del args
    root = paths.root()
    benchmarks = loader.load_all(root)
    if not benchmarks:
        print(f"no benchmarks in {paths.gold_dir(root)}")
        return 0
    for benchmark in benchmarks:
        for task in benchmark.tasks:
            print(f"{benchmark.name}  {task.describe()}")
    return 0


def cmd_sandbox_build(args: argparse.Namespace) -> int:
    claude_code = args.claude_code_version or sandbox.installed_version("claude", "--claude-code-version")
    opencode = args.opencode_version or sandbox.installed_version("opencode", "--opencode-version")
    sandbox.build(paths.checkout_root(), claude_code=claude_code, opencode=opencode, tag=args.tag)
    print(f"image {args.tag}  claude-code {claude_code}  opencode {opencode}")
    return 0


def _logins(args: argparse.Namespace) -> dict[str, Path]:
    given = {"claude": args.credentials, "opencode": args.opencode_auth}
    clis = sandbox.config_clis(args.config)
    unknown = sorted(clis - given.keys())
    if unknown:
        raise SandboxError(
            f"{args.config} runs {', '.join(unknown)}, which the sandbox has no login for. "
            + f"Point the config's profiles at one of {', '.join(sorted(given))}"
        )
    return {cli: given[cli] for cli in clis}


def _command_after_separator(given: list[str]) -> list[str]:
    command = given[1:] if given[:1] == ["--"] else given
    if not command:
        raise SandboxError("no command to run. Put it after `--`, as in `paddock sandbox run ... -- workhorse-okf-book run`")
    return command


def cmd_sandbox_run(args: argparse.Namespace) -> int:
    command = _command_after_separator(args.command)
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    box = Sandbox(
        app=args.app,
        runs_dir=args.runs_dir,
        config=args.config,
        logins=_logins(args),
        image=args.image,
        base_library=args.base_library,
        home_skills=sandbox.home_skills(Path.home()),
    )
    refused = box.refusals(paths.checkout_root())
    if refused:
        raise SandboxError("the sandbox would not be isolated:\n" + "\n".join(refused))
    argv = box.docker_run_argv(command, uid=os.getuid(), gid=os.getgid(), name=args.name)
    return subprocess.run(argv, check=False).returncode


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    try:
        raise SystemExit(args.handler(args))
    except (HomeConfigError, TaskError, RunError, SandboxError) as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
