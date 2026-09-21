"""`run` — the arguments it takes and the invocation it builds."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse import otel
from workhorse._vendor.stablemate_core.config import (
    CONFIG_PATH_ENV,
    ConfigError,
    UnknownProfileError,
    config_path,
    get_config_value,
    load_config,
    profile_backends,
    profile_has_backend,
    resolve_default_cli,
    select_active_profile,
    select_profile,
)
from workhorse._vendor.stablemate_core.discovery import base_library_dir
from workhorse.cli.params import load_params
from workhorse.config_run import RunConfig
from workhorse.manifest import load_context_manifest as _load_context_manifest
from workhorse.packaged import PackagedWorkflowError
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.records import parse_run_record
from workhorse.rundir import find_latest_resumable as _find_latest_resumable
from workhorse.rundir import resolve_run_dir
from workhorse.runner.backends.registry import backend_names, get_backend

NAME = "run"
HELP = "Execute a workflow (default)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "flow",
        nargs="?",
        default=None,
        help="The flow sub-graph to run standalone (e.g. 'qa'). Omit it to start the "
        "workflow at its entry flow.",
    )
    parser.add_argument(
        "--context-file",
        default=None,
        metavar="PATH",
        help="Per-repo farrier context manifest (JSON). Default: "
        "$AGENT_REPO_DIR/.agents/agents-context.json. Provides the template "
        "values, instruction/prompt path maps, and selected-skills set the "
        "library prompts render against. Required.",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Directory to write run artifacts (default: <cwd>/.agents/runs — "
        "deduced from the directory workhorse is launched in)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Name the stable run dir (<workflow>-<run-id>). Default: a digest of "
        "--params (so distinct params get distinct dirs and never collide on one "
        "run), or 'default' when no params are given. Use distinct ids to keep "
        "separate runs of the same workflow side by side.",
    )
    parser.add_argument(
        "--params",
        default=None,
        metavar="JSON",
        help="Inline JSON object of workflow params (key→value) merged into the "
        "starting context, overriding the workflow's own vars. Combined with "
        "--params-file when both are given (inline wins).",
    )
    parser.add_argument(
        "--params-file",
        default=None,
        metavar="PATH",
        help="Path to a JSON file of workflow params (same effect as --params).",
    )
    parser.add_argument(
        "--cli",
        default=None,
        metavar="NAME",
        help="Agent CLI backend to drive this run: claude, codex, copilot, cline, or "
        "opencode. Overrides the AGENT_CLI env var, which in turn overrides the "
        "shared config's `default_cli` (claude when that is unset too). Selection is "
        "per-run, not per-node. To run on an OpenRouter model, use an OpenRouter-"
        "native backend (cline/opencode) and give nodes an 'openrouter/<slug>' model. "
        "MUTUALLY EXCLUSIVE with --profile: a profile carries its own `cli` field, "
        "and the two cannot disagree about which CLI runs.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help="Resolve this run's models from the named [profiles.NAME] table. The "
        "profile REPLACES the top-level model tables — nothing outside it is "
        "inherited — and declares its own `cli` field naming the CLI it runs "
        "under. MUTUALLY EXCLUSIVE with --cli: drop --cli, or the profile selects "
        "its CLI for you. A profile whose key matches its `cli` is auto-selected "
        "when `--cli <that-cli>` is set without `--profile`.",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Read the shared stablemate config from this file instead of the "
        "discovered one. Means what $STABLEMATE_CONFIG means: THIS file, entirely — "
        "no merge with the machine's config, so it must itself carry library_dir / "
        "base_dir / stablemate_dir if the run needs them. Overrides "
        "$STABLEMATE_CONFIG, which in turn overrides $WORKHORSE_CONFIG.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the workflow without running it, and exit non-zero if anything "
        "is wrong. Every prompt path must resolve, every state name must bind and "
        "no state may be unreachable; nodes and agent turns are stubbed. The "
        "failure this catches is a typo found at hour 30 of an unattended run.",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Cut a fresh branch and git worktree for this run and dispatch it "
        "there instead of the invoking repo. Requires a configured worktree_dir "
        "(see `farrier config set-worktree`). Ignored, with a printed note, on a "
        "--resume-run/--resume-latest of a run that already recorded one — the "
        "recorded worktree is used as-is.",
    )
    parser.add_argument(
        "--worktree-branch",
        default=None,
        metavar="NAME",
        help="Override the default 'run/<workflow>-<run-id>' branch name cut by "
        "--worktree. Meaningless without --worktree.",
    )
    parser.add_argument(
        "--worktree-base",
        default=None,
        metavar="REF",
        help="Override the base ref --worktree branches from (default: HEAD of "
        "the invoking repo). Meaningless without --worktree.",
    )
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume-run",
        default=None,
        metavar="PATH_OR_RUN_ID",
        help="Resume a crashed run from its checkpoint. Accepts a run directory "
        "path or a run-dir name under --runs-dir.",
    )
    resume_group.add_argument(
        "--resume-latest",
        action="store_true",
        help="Resume the most recent unfinished run under --runs-dir (errors if none).",
    )
    resume_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Delete the stable run directory before starting, forcing a clean run "
        "from scratch. Mutually exclusive with --resume-run and --resume-latest.",
    )


def run(args: argparse.Namespace) -> None:
    sys.exit(run_pyflow(invocation(args)))


def invocation(args: argparse.Namespace) -> RunInvocation:
    """Everything `run` decided, as the one value the driver is handed."""
    registry: Registry = args.registry
    try:
        registry.directory()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    flow = args.flow

    _apply_config_path(getattr(args, "config", None))

    os.environ.setdefault("AGENT_REPO_DIR", str(Path.cwd().resolve()))

    if args.cli and getattr(args, "profile", None):
        print(
            "error: --cli and --profile are mutually exclusive — a profile carries "
            "its own `cli` field. Drop one of them.",
            file=sys.stderr,
        )
        sys.exit(2)

    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (Path.cwd() / ".agents" / "runs").resolve()
    resume_run_dir = _resume_run_dir(args, runs_dir, registry.name)

    profile_name = (getattr(args, "profile", None) or "").strip()
    if not profile_name and not args.cli and resume_run_dir is not None:
        profile_name = _recorded_profile(resume_run_dir)
    cfg = load_config()
    try:
        if profile_name:
            profile = select_profile(cfg, profile_name)
            resolved_cli = _profile_cli_or_raise(profile, profile_name)
        else:
            active_cli = _resolve_active_cli(args, cfg)
            profile = select_active_profile(cfg, active_cli=active_cli)
            resolved_cli = active_cli
    except UnknownProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    os.environ["AGENT_CLI"] = resolved_cli

    try:
        backend = get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    _check_profile_resolves(profile_name, profile, backend.name)

    params = load_params(args.params, args.params_file)
    params.setdefault("repo_dir", os.environ.get("AGENT_REPO_DIR") or str(Path.cwd().resolve()))
    params.setdefault("library_dirs", library_dirs(cfg))

    return RunInvocation(
        registry=registry,
        runs_dir=runs_dir,
        flow=flow,
        run_id=args.run_id,
        params=params,
        resume_run_dir=resume_run_dir,
        no_cache=getattr(args, "no_cache", False),
        dry_run=getattr(args, "dry_run", False),
        context_manifest=_load_context_manifest(args.context_file),
        worktree=getattr(args, "worktree", False),
        worktree_branch=getattr(args, "worktree_branch", None),
        worktree_base=getattr(args, "worktree_base", None),
        config=replace(
            RunConfig.from_env(os.environ), backend=backend, profile=profile_name
        ),
        telemetry=otel.TelemetryHost(otel.OtelSettings.from_env(os.environ)),
    )


def library_dirs(cfg: dict[str, Any]) -> list[str]:
    """The library roots this run resolves content against, highest precedence first."""
    roots: list[str] = []
    overlay = os.environ.get("FARRIER_LIBRARY_DIR") or get_config_value("library_dir", cfg)
    for candidate in (overlay, base_library_dir()):
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if path.is_dir() and str(path) not in roots:
            roots.append(str(path))
    return roots


def _resolve_active_cli(args: argparse.Namespace, cfg: dict[str, Any]) -> str:
    """Resolve the active CLI for a non-`--profile` run: --cli → $AGENT_CLI → config."""
    return (
        args.cli
        or os.environ.get("AGENT_CLI")
        or resolve_default_cli(cfg)
    ).strip().lower()


def _profile_cli_or_raise(profile: dict[str, Any], name: str) -> str:
    """The CLI a `--profile`-selected profile declares, stripped and lowercased."""
    cli = profile.get("cli")
    if not isinstance(cli, str) or not cli.strip():
        raise ConfigError(f"[profiles.{name}] has no cli field")
    return cli.strip().lower()


def _check_profile_resolves(name: str, profile: dict[str, Any], backend: str) -> None:
    """Refuse a selected profile whose `cli` field names a backend workhorse does not drive."""
    if not name:
        return
    consulted = f"(in {config_path()})"

    unknown = [n for n in profile_backends(profile) if n not in backend_names()]
    if unknown:
        print(
            f"error: profile {name!r} declares cli = {unknown[0]!r} {consulted}; that "
            f"is not a backend this build of workhorse drives. Known backends: "
            f"{', '.join(backend_names())}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not profile_has_backend(profile, backend):
        print(
            f"error: profile {name!r} declares cli = {backend!r} but carries no "
            f"models for it {consulted}. Add a [profiles.{name}.powers.<tier>] "
            f"table or a [profiles.{name}.default] entry, or run with --cli "
            f"<this-cli> and no --profile (bare-CLI mode).",
            file=sys.stderr,
        )
        sys.exit(1)


def _apply_config_path(raw: str | None) -> None:
    """Point the whole process at the config `--config` named, or leave discovery alone."""
    if not raw:
        return
    path = Path(raw).expanduser()
    if not path.is_file():
        print(f"error: --config {raw}: no such file", file=sys.stderr)
        sys.exit(1)
    os.environ[CONFIG_PATH_ENV] = str(path.resolve())


def _recorded_profile(run_dir: Path) -> str:
    """The profile a run was started under, read back off its `run.json`."""
    try:
        return parse_run_record((run_dir / "run.json").read_text()).profile
    except (OSError, ValidationError):
        return ""


def _resume_run_dir(
    args: argparse.Namespace, runs_dir: Path, workflow_name: str
) -> Path | None:
    """The run dir an explicit `--resume-run` / `--resume-latest` names, if either was given."""
    if args.resume_run:
        resolved = resolve_run_dir(args.resume_run, runs_dir, workflow_name)
        if resolved is None:
            print(
                f"error: resume run dir not found for {args.resume_run!r} "
                f"(looked under {runs_dir})",
                file=sys.stderr,
            )
            sys.exit(1)
        return resolved

    if args.resume_latest:
        latest = _find_latest_resumable(runs_dir)
        if latest is None:
            print(f"error: no resumable run found under {runs_dir}", file=sys.stderr)
            sys.exit(1)
        return latest

    return None
