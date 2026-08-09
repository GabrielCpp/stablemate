"""`run` — the arguments it takes and the invocation it builds.

Everything here is the CLI's contract rather than any engine's: which flow, the repo
dir, the backend, the runs dir, params, the context manifest and the resume flags. It
ends by handing the driver one :class:`RunInvocation`.

*Which workflow* is not among them. The console script that reached this module is the
workflow's own, and it hands its `Registry` in — so there is no name to resolve, and no
way for this command to be pointed at a different workflow than the one it is.

This is also the process's one environment read. `AGENT_*` and `WORKHORSE_*` become a
`RunConfig` and a `TelemetryHost` here, and travel on the invocation; nothing the
driver calls goes back to `os.environ` for them.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from workhorse import otel
from workhorse.cli.params import load_params
from workhorse.config_run import RunConfig
# Bound under its historical private name, which is also what lets a test patch the
# loader on this module and have the CLI see it.
from workhorse.manifest import load_context_manifest as _load_context_manifest
from workhorse.packaged import PackagedWorkflowError
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
# Re-imported under its historical private name: the run-identity rules live in
# `rundir` so the driver can obey them without importing this module.
from workhorse.rundir import find_latest_resumable as _find_latest_resumable
from workhorse.rundir import resolve_run_dir
from workhorse.runner.backends.registry import get_backend

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
        help="Agent CLI backend to drive this run: claude (default), codex, copilot, "
        "cline, or opencode. Overrides the AGENT_CLI env var. Selection is per-run, "
        "not per-node. To run on an OpenRouter model, use an OpenRouter-native "
        "backend (cline/opencode) and give nodes an 'openrouter/<slug>' model.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the workflow without running it, and exit non-zero if anything "
        "is wrong. Every prompt path must resolve, every state name must bind and "
        "no state may be unreachable; nodes and agent turns are stubbed. The "
        "failure this catches is a typo found at hour 30 of an unattended run.",
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
    # The console script holds its own workflow and hands it in — the CLI never looks
    # one up. `directory()` is asked for here rather than at the first prompt render,
    # so a package installed in a shape whose prompts can't be read (a zipapp, a
    # zip-safe egg) says so now instead of as a `TemplateNotFound` several nodes in.
    registry: Registry = args.registry
    try:
        registry.directory()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    flow = args.flow

    # The consuming repo is the directory workhorse is launched in — same <cwd> rule
    # as the runs-dir default below. Pin AGENT_REPO_DIR to the launch dir when the
    # caller hasn't set it, so every *subprocess* (the agent CLI and whatever it
    # shells out to) agrees on the repo without needing the farrier Makefile.
    #
    # The workflow itself does not read it: this is the boundary, and what crosses it
    # is `repo_dir`, resolved below and handed over as a run parameter.
    os.environ.setdefault("AGENT_REPO_DIR", str(Path.cwd().resolve()))

    # --cli (else AGENT_CLI, else default claude) selects the backend for the run.
    if args.cli:
        os.environ["AGENT_CLI"] = args.cli

    # Resolve the active backend now so an unknown name fails fast with a clear
    # message instead of mid-run — and because this is the ring that gets to know
    # adapters exist. What travels on the invocation is the adapter itself, so
    # nothing further in has to reach back to the registry to find one.
    try:
        backend = get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (Path.cwd() / ".agents" / "runs").resolve()

    # Default behavior is auto: a single stable run dir per program that is resumed
    # in place (continuing the same session/context), or started fresh in that dir
    # if absent. The explicit --resume-run/--resume-latest flags below are manual
    # overrides that target a specific dir instead. auto stays on either way — when
    # resume_run_dir is set, the driver uses it directly and skips auto resolution.
    # `repo_dir` is `Workflow`'s one universal input, and this is the only place it is
    # resolved: the environment is read *here*, at the edge, so that everything inside
    # the run receives it as an ordinary parameter. An explicit `--param repo_dir=…`
    # wins, which is what makes a run against a checkout other than the launch
    # directory expressible at all.
    params = load_params(args.params, args.params_file)
    params.setdefault("repo_dir", os.environ.get("AGENT_REPO_DIR") or str(Path.cwd().resolve()))

    return RunInvocation(
        registry=registry,
        runs_dir=runs_dir,
        flow=flow,
        run_id=args.run_id,
        params=params,
        resume_run_dir=_resume_run_dir(args, runs_dir, registry.name),
        no_cache=getattr(args, "no_cache", False),
        dry_run=getattr(args, "dry_run", False),
        context_manifest=_load_context_manifest(args.context_file),
        # Read last, after `--cli` and the repo-dir default above have had their say,
        # so what the run is given is the environment as the CLI finally settled it.
        config=replace(RunConfig.from_env(os.environ), backend=backend),
        telemetry=otel.TelemetryHost(otel.OtelSettings.from_env(os.environ)),
    )


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
