"""`workhorse run` — the arguments it takes and the invocation it builds.

Everything here is the CLI's contract rather than any engine's: which workflow and
flow, the repo dir, the backend, the runs dir, params, the context manifest and the
resume flags. It ends by handing the driver one :class:`RunInvocation`.

This is also the process's one environment read. `AGENT_*` and `WORKHORSE_*` become a
`RunConfig` and a `TelemetryHost` here, and travel on the invocation; nothing the
driver calls goes back to `os.environ` for them.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from workhorse import otel
from workhorse.cli.params import load_params
from workhorse.cli.resolve import packaged_registry
from workhorse.config_run import RunConfig
# Bound under its historical private name, which is also what lets a test patch the
# loader on this module and have the CLI see it.
from workhorse.manifest import load_context_manifest as _load_context_manifest
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
# Re-imported under its historical private name: the run-identity rules live in
# `rundir` so the driver can obey them without importing this module.
from workhorse.rundir import find_latest_resumable as _find_latest_resumable
from workhorse.runner.backends.registry import get_backend

NAME = "run"
HELP = "Execute a workflow (default)"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow",
        default=None,
        help="The workflow NAME (e.g. 'coder') — an installed package registering it "
        "in the 'workhorse.workflows' entry-point group. Not a path: a workflow is a "
        "Python package, not a file. May also be given as the first positional "
        "argument: `workhorse run coder` or `workhorse run coder qa`.",
    )
    parser.add_argument(
        "positional",
        nargs="*",
        help="Positional form of --workflow [flow]: `workhorse run <name> [<flow>]`. "
        "The first token is treated as the workflow name when --workflow is omitted; "
        "the optional second token is the flow sub-graph to run standalone.",
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
        "aider, or opencode. Overrides the AGENT_CLI env var. Selection is per-run, "
        "not per-node. To run on an OpenRouter model, use an OpenRouter-native "
        "backend (aider/opencode) and give nodes an 'openrouter/<slug>' model.",
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
    workflow_spec, flow = _workflow_and_flow(args)

    # A `workhorse-<name>` console script already holds its Registry (it never went
    # through discovery), so it hands it in; a bare name resolves one from the entry
    # point.
    registry: Registry = getattr(args, "registry", None) or packaged_registry(
        workflow_spec
    )

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

    # Validate the active backend now so an unknown name fails fast with a clear
    # message instead of mid-run.
    try:
        get_backend()
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
        config=RunConfig.from_env(os.environ),
        telemetry=otel.TelemetryHost(otel.OtelSettings.from_env(os.environ)),
    )


def _workflow_and_flow(args: argparse.Namespace) -> tuple[str, str | None]:
    """The workflow name and optional flow, from the two input shapes.

    Two same-typed values, so they would normally want a record — but this is the pair
    ``--workflow [flow]`` is *written* as, and it is consumed on the next line rather
    than carried anywhere.

    ``explicit``    ``--workflow coder [--flow qa]``  (args.workflow set, positional empty)
    ``positional``  ``coder [qa]``                    (args.workflow None, positional both)
    """
    workflow_spec = args.workflow
    flow = getattr(args, "flow", None)  # legacy: flow used to be its own positional
    positional = getattr(args, "positional", []) or []
    if workflow_spec is None:
        if not positional:
            print(
                "error: workflow is required — pass --workflow <name> or use the "
                "positional form: workhorse run <name> [<flow>]",
                file=sys.stderr,
            )
            sys.exit(1)
        workflow_spec = positional[0]
        if len(positional) > 1:
            flow = positional[1]
    elif positional:
        # --workflow given AND positionals present → first positional is the flow
        if len(positional) == 1:
            flow = positional[0]
        else:
            print(
                f"error: unexpected positional arguments {positional[1:]!r} — "
                "when --workflow is given, at most one positional (the flow name) is allowed",
                file=sys.stderr,
            )
            sys.exit(1)
    return workflow_spec, flow


def _resume_run_dir(
    args: argparse.Namespace, runs_dir: Path, workflow_name: str
) -> Path | None:
    """The run dir an explicit `--resume-run` / `--resume-latest` names, if either was given."""
    if args.resume_run:
        # Three spellings, because the flag's own metavar promises two and `--run-id`
        # creates the third: a path, the run *dir* name, and the run id that named it.
        # A dir is `<workflow>-<run-id>`, so `--run-id shakedown --resume-run shakedown`
        # — the obvious thing to type — used to miss the dir it had just made.
        candidate = Path(args.resume_run)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = runs_dir / args.resume_run
            if not candidate.is_dir():
                candidate = runs_dir / f"{workflow_name}-{args.resume_run}"
        resolved = candidate.resolve()
        if not resolved.is_dir():
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
