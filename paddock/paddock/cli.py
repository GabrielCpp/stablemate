"""The `paddock` command line."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from paddock import loader, paths, sandbox, seeds
from paddock.pointer import Pointer, PointerError, describe
from paddock.registry import TaskError
from paddock.runner import RunError, execute
from paddock.sandbox import Sandbox, SandboxError
from paddock.seeds import SeedError

logger = logging.getLogger("paddock")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paddock", description="Run a benchmark task.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="tracked benchmark data (tasks, pointers, configs); default: <repo>/benchmarks",
    )
    parser.add_argument(
        "--store", type=Path, default=paths.STORE, help=f"where zips live; default: {paths.STORE}"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="capture and unpack repo states").add_subparsers(
        dest="seed_command", required=True
    )

    capture = seed.add_parser("capture", help="zip a repo as it stands into a named seed")
    capture.add_argument("repo", type=Path)
    capture.add_argument("--name", required=True)
    capture.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="path or name to leave out; also permits a directory the junk scan refuses",
    )
    capture.add_argument("--url", default="", help="https url the zip will be served from (kept on re-capture if omitted)")
    capture.add_argument("--note", default="", help="one line on what state this captures (kept on re-capture if omitted)")
    capture.add_argument("--force", action="store_true", help="replace an existing seed")
    capture.set_defaults(handler=cmd_capture)

    unpack = seed.add_parser("unpack", help="put a seed on disk, verified")
    unpack.add_argument("name")
    unpack.add_argument("--to", type=Path, required=True, dest="dest")
    unpack.add_argument(
        "--no-install",
        action="store_true",
        help="skip re-running farrier install; the tree keeps the capture machine's paths",
    )
    unpack.set_defaults(handler=cmd_unpack)

    fetch = sub.add_parser("fetch", help="download a seed's zip into the local store")
    fetch.add_argument("name")
    fetch.add_argument("--force", action="store_true", help="re-download even if it is present")
    fetch.set_defaults(handler=cmd_fetch)

    run = sub.add_parser("run", help="run a task end to end")
    run.add_argument("task")
    run.add_argument("--label", default="", help="names the result; default: the task name")
    run.add_argument("--no-seal", action="store_true", help="leave the staging area, write no zip")
    run.add_argument("--keep", action="store_true", help="reuse the existing work directory")
    run.add_argument(
        "--no-pin-project",
        action="store_true",
        help="drive the checkout in place instead of a worktree pinned at its HEAD",
    )
    run.add_argument(
        "--quiet",
        action="store_true",
        help="do not tee each command's output to stderr as it is written",
    )
    run.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="a knob the task reads with run.param(); repeatable",
    )
    run.set_defaults(handler=cmd_run)

    listing = sub.add_parser("list", help="tasks and seeds in the data directory")
    listing.set_defaults(handler=cmd_list)

    sandbox_commands = sub.add_parser(
        "sandbox", help="run a command where stablemate is installed as packages and its checkout is absent"
    ).add_subparsers(dest="sandbox_command", required=True)

    sandbox_build = sandbox_commands.add_parser("build", help="build the sandbox image from this checkout's packages")
    sandbox_build.add_argument("--tag", default=sandbox.IMAGE)
    sandbox_build.add_argument(
        "--claude-code-version", default="", help="the Claude Code release to install; default: this machine's"
    )
    sandbox_build.set_defaults(handler=cmd_sandbox_build)

    sandbox_run = sandbox_commands.add_parser(
        "run",
        help="run a command in the app, inside the sandbox",
        description=(
            f"The app is mounted at {sandbox.WORK}/<its directory name> and is the working directory, "
            + f"--runs-dir at {sandbox.RUNS}, and --config at {sandbox.CONFIG}. Nothing else of this machine is visible."
        ),
    )
    sandbox_run.add_argument("--app", type=Path, required=True, help="the repo the command works on")
    sandbox_run.add_argument("--runs-dir", type=Path, required=True, help="where the command writes its runs")
    sandbox_run.add_argument("--config", type=Path, required=True, help="the stablemate config the command reads")
    sandbox_run.add_argument(
        "--credentials",
        type=Path,
        default=Path.home() / ".claude" / ".credentials.json",
        help="the Claude Code login the agents use",
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
    return parser


def _data_dir(args: argparse.Namespace) -> Path:
    return (args.data_dir or paths.default_data_dir()).resolve()


def _store(args: argparse.Namespace) -> Path:
    """Absolute, because a task hands store-relative paths to subprocesses it runs under another cwd."""
    return Path(args.store).resolve()


def _params(given: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in given:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise RunError(f"--param must be KEY=VALUE, got {item!r}")
        params[key.strip()] = value
    return params


def _project(data_dir: Path) -> Path:
    """The uv project farrier is run out of — the repo the data directory belongs to."""
    return paths.repo_root(data_dir)


def cmd_capture(args: argparse.Namespace) -> int:
    data_dir = _data_dir(args)
    captured = seeds.capture(
        args.repo,
        name=args.name,
        data_dir=data_dir,
        store=_store(args),
        excludes=tuple(args.exclude),
        url=args.url,
        note=args.note,
        force=args.force,
    )
    print(f"seed {describe(captured.pointer)}")
    print(f"  zip     {captured.zip_path}")
    print(f"  pointer {captured.pointer_path}")
    if not captured.pointer.url:
        print("  no url: this seed only exists on this machine until one is added")
    return 0


def cmd_unpack(args: argparse.Namespace) -> int:
    data_dir = _data_dir(args)
    pointer = Pointer.load(paths.seed_pointer(data_dir, args.name))
    repo = seeds.unpack(
        pointer,
        store=_store(args),
        dest=args.dest.resolve(),
        install=not args.no_install,
        project=_project(data_dir),
    )
    print(repo)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    data_dir = _data_dir(args)
    pointer = Pointer.load(paths.seed_pointer(data_dir, args.name))
    print(seeds.fetch(pointer, store=_store(args), force=args.force))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    data_dir = _data_dir(args)
    task = loader.load_named(data_dir, args.task)
    label = args.label or task.name
    result = execute(
        task,
        label=label,
        data_dir=data_dir,
        store=_store(args),
        params=_params(args.param),
        project=_project(data_dir),
        pin_project=not args.no_pin_project,
        seal=not args.no_seal,
        echo=not args.quiet,
    )
    for outcome in result.outcomes:
        mark = {"ok": "ok  ", "failed": "FAIL", "skipped": "skip"}[outcome.status]
        print(f"{mark} {outcome.name}  {outcome.seconds:.1f}s{'  ' + outcome.error if outcome.error else ''}")
    if result.score is not None:
        print(result.score.render())
    print(f"stage   {result.stage}")
    if result.zip_path:
        print(f"result  {result.zip_path}")
        print(f"pointer {result.pointer_path}")
    return 0 if result.ok else 1


def cmd_list(args: argparse.Namespace) -> int:
    data_dir = _data_dir(args)
    tasks = loader.load_all(data_dir)
    if not tasks:
        print(f"no tasks in {paths.tasks_dir(data_dir)}")
        return 0
    for task in tasks:
        print(task.describe())
        pointer_path = paths.seed_pointer(data_dir, task.seed)
        if not pointer_path.exists():
            print(f"    seed pointer missing: {pointer_path}")
            continue
        pointer = Pointer.load(pointer_path)
        present = paths.seed_zip(_store(args), pointer.name).exists()
        print(f"    {describe(pointer)}  [{'local' if present else 'not fetched'}]")
    return 0


def cmd_sandbox_build(args: argparse.Namespace) -> int:
    version = args.claude_code_version or sandbox.claude_code_version()
    sandbox.build(_project(_data_dir(args)), claude_code=version, tag=args.tag)
    print(f"image {args.tag}  claude-code {version}")
    return 0


def _command(given: list[str]) -> list[str]:
    command = given[1:] if given[:1] == ["--"] else given
    if not command:
        raise SandboxError("no command to run. Put it after `--`, as in `paddock sandbox run ... -- workhorse-okf-book run`")
    return command


def cmd_sandbox_run(args: argparse.Namespace) -> int:
    command = _command(args.command)
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    box = Sandbox(
        app=args.app,
        runs_dir=args.runs_dir,
        config=args.config,
        credentials=args.credentials,
        image=args.image,
        base_library=args.base_library,
    )
    refused = box.refusals(_project(_data_dir(args)))
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
    except (SeedError, PointerError, TaskError, RunError, SandboxError) as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
