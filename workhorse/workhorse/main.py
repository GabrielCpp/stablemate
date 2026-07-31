"""The `workhorse` command line — argument parsing, resolution, and dispatch.

This module used to be the YAML graph walk *and* the CLI around it. The graph walk
is gone; what remains is the front door. It resolves a workflow name to the Python
state machine registered for it, assembles the things a run needs that are the
CLI's contract rather than any engine's (the repo dir, the backend, the runs dir,
params, the context manifest, the resume flags), and hands them to
:func:`workhorse.pyflow.run.run_pyflow`. The other subcommands — `test`, `dot`,
`config`, `version` — are here for the same reason: one parser, one front door.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from stablemate_core.discovery import is_library_dir as _is_base_library_dir
from stablemate_core.config import (
    ConfigVersionError,
    config_path,
    get_config_value,
    load_config,
    write_config_key,
)
# Bound under its historical private name, which is also what lets a test patch the
# loader on this module and have the CLI see it.
from workhorse.manifest import load_context_manifest as _load_context_manifest
from workhorse.packaged import (
    PackagedWorkflowError,
    find_packaged_workflow,
    installed_workflow_names,
)
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import run_pyflow
# Re-imported under its historical private name: the run-identity rules live in
# `rundir` so the driver can obey them without importing this module.
from workhorse.rundir import find_latest_resumable as _find_latest_resumable

def _load_params(inline: str | None, file: str | None) -> dict[str, Any]:
    """Merge workflow params from --params-file then --params (inline wins).

    Each source must be a JSON object (key→value map). Exits with a clear error on
    a missing file, invalid JSON, or a non-object payload."""
    params: dict[str, Any] = {}
    if file is not None:
        try:
            inline_from_file = Path(file).read_text()
        except OSError as e:
            print(f"error: cannot read --params-file {file}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        inline_from_file = None

    for label, raw in (("--params-file", inline_from_file), ("--params", inline)):
        if raw is None:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed, dict):
            print(
                f"error: {label} must be a JSON object (key→value map)", file=sys.stderr
            )
            sys.exit(1)
        params.update(parsed)
    return params



def _add_run_args(parser: argparse.ArgumentParser) -> None:
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

def _packaged_registry(spec: str) -> Registry:
    """The installed Python :class:`Registry` a workflow name resolves to.

    A name resolves in exactly one place: an installed distribution registering it in
    the ``workhorse.workflows`` entry-point group, whose entry point is a ``Registry``.
    There is no second mechanism. Until the YAML front-end was removed a name could
    also name a `workflow.yaml` under a library layer, and a path could be passed
    verbatim; both are gone with the loader that read them, so the errors below say so
    rather than reporting the name as merely unknown."""
    try:
        packaged = find_packaged_workflow(spec)
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if packaged is None:
        known = ", ".join(sorted(installed_workflow_names())) or "(none installed)"
        hint = (
            "\nWorkflows are Python packages now, not workflow.yaml files — a path is "
            "not a workflow.\n"
            if _looks_like_path(spec)
            else ""
        )
        print(
            f"error: no workflow named '{spec}' is installed.{hint}"
            f"Installed workflows: {known}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target = packaged.load()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(target, Registry):
        print(
            f"error: workflow '{packaged.name}' resolves to {packaged.origin}, whose "
            f"entry point is a {type(target).__name__}, not a `Registry`.\n"
            f"Check what '{packaged.value}' actually points at.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ask for the directory now, while the operator is still being told about
    # resolution. `Registry.directory` is what refuses a zip-imported package, and
    # deferring it to the first prompt render turns "this wheel is packed wrong" into a
    # TemplateNotFound several nodes into a run.
    try:
        target.directory()
    except PackagedWorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    return target


def _looks_like_path(spec: str) -> bool:
    """Whether a ``--workflow`` value was written as a path rather than a bare name."""
    return (
        os.sep in spec
        or (os.altsep is not None and os.altsep in spec)
        or spec.endswith((".yaml", ".yml"))
        or Path(spec).exists()
    )


def _run_run(args: argparse.Namespace) -> None:
    # Resolve workflow name/path and optional flow from the two input shapes:
    #   explicit:   --workflow coder [--flow qa]  (args.workflow set, args.positional=[])
    #   positional: coder [qa]                    (args.workflow=None, args.positional=[name, flow?])
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

    # A `workhorse-<name>` console script already holds its Registry (it never went
    # through discovery), so it hands it in; a bare name resolves one from the entry
    # point. Everything after this point — the repo dir, the backend, the runs dir,
    # params, the resume flags — is the CLI's contract rather than the driver's, which
    # is why it is assembled here and not in `run_pyflow`.
    registry: Registry = getattr(args, "registry", None) or _packaged_registry(
        workflow_spec
    )

    # The consuming repo is the directory workhorse is launched in — same <cwd> rule
    # as the runs-dir default below. A workflow's scripts resolve the repo root from
    # AGENT_REPO_DIR first and only fall back to walking up from their cwd, and that
    # walk finds whatever directory the installed workflow package happens to sit in
    # rather than the target repo. Pin AGENT_REPO_DIR to the launch dir when the
    # caller hasn't set it, so every subprocess agrees on the repo without needing
    # the farrier Makefile.
    os.environ.setdefault("AGENT_REPO_DIR", str(Path.cwd().resolve()))

    # --cli (else AGENT_CLI, else default claude) selects the backend for the run.
    if args.cli:
        os.environ["AGENT_CLI"] = args.cli

    # Validate the active backend now so an unknown name fails fast with a clear
    # message instead of mid-run.
    from workhorse.runner.backends import get_backend

    try:
        get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (Path.cwd() / ".agents" / "runs").resolve()

    params = _load_params(args.params, args.params_file)
    context_manifest = _load_context_manifest(args.context_file)

    resume_run_dir: Path | None = None
    if args.resume_run:
        candidate = Path(args.resume_run)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = runs_dir / args.resume_run
        resume_run_dir = candidate.resolve()
        if not resume_run_dir.is_dir():
            print(f"error: resume run dir not found: {resume_run_dir}", file=sys.stderr)
            sys.exit(1)
    elif args.resume_latest:
        resume_run_dir = _find_latest_resumable(runs_dir)
        if resume_run_dir is None:
            print(f"error: no resumable run found under {runs_dir}", file=sys.stderr)
            sys.exit(1)

    # Default behavior is auto: a single stable run dir per program that is resumed
    # in place (continuing the same session/context), or started fresh in that dir
    # if absent. The explicit --resume-run/--resume-latest flags above are manual
    # overrides that target a specific dir instead. auto stays on either way — when
    # resume_run_dir is set, the driver uses it directly and skips auto resolution.
    sys.exit(
        run_pyflow(
            registry,
            flow,
            runs_dir=runs_dir,
            resume_run_dir=resume_run_dir,
            run_id=args.run_id,
            params=params,
            no_cache=getattr(args, "no_cache", False),
            dry_run=getattr(args, "dry_run", False),
            context_manifest=context_manifest,
        )
    )


def _add_test_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "workflow_dir",
        help="Directory containing workflow.yaml and a tests/ subdirectory",
    )
    parser.add_argument(
        "--filter",
        "-k",
        default=None,
        metavar="PATTERN",
        help="Only run tests matching this pytest -k expression",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Pass -v to pytest for verbose output",
    )


def _run_test(args: argparse.Namespace) -> None:
    workflow_dir = Path(args.workflow_dir).resolve()
    tests_dir = workflow_dir / "tests"
    if not tests_dir.is_dir():
        print(f"error: no tests/ directory found in {workflow_dir}", file=sys.stderr)
        sys.exit(1)
    try:
        import pytest as _pytest  # noqa: PLC0415
    except ImportError:
        print(
            "error: pytest is required to run workflow tests.\n"
            "Install it with: pip install 'workhorse-agent[test]'",
            file=sys.stderr,
        )
        sys.exit(1)
    pytest_args = [str(tests_dir)]
    if args.filter:
        pytest_args += ["-k", args.filter]
    if args.verbose:
        pytest_args += ["-v"]
    sys.exit(_pytest.main(pytest_args))


def _add_dot_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow",
        default=None,
        help="The workflow NAME, resolved the same way `run` resolves one. Rendered "
        "from its states, one cluster per flow.",
    )
    parser.add_argument(
        "positional",
        nargs="*",
        help="Positional form of --workflow: `workhorse dot <name>`.",
    )
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="Override the digraph identifier (default: sanitized workflow name).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Write the DOT output to this file (default: stdout).",
    )


def _dot_spec(args: argparse.Namespace) -> str:
    """The workflow `dot` was asked for, from --workflow or the positional form."""
    positional = list(getattr(args, "positional", None) or [])
    spec = args.workflow or (positional.pop(0) if positional else None)
    if positional:
        print(f"error: unexpected argument '{positional[0]}'", file=sys.stderr)
        sys.exit(1)
    if not spec:
        print("error: dot needs a workflow name", file=sys.stderr)
        sys.exit(1)
    return spec


def _run_dot(args: argparse.Namespace) -> None:
    """Render a workflow's state machine as DOT, one cluster per flow."""
    from workhorse.pyflow.dot import to_dot
    from workhorse.pyflow.graph import registry_graphs

    spec = _dot_spec(args)
    registry = getattr(args, "registry", None) or _packaged_registry(spec)
    dot = to_dot(registry_graphs(registry), name=args.name or registry.name)

    if args.output:
        Path(args.output).write_text(dot)
        print(f"[workhorse] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(dot)


def _build_parser(prog: str = "workhorse") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Fail-soft runner for agent workflows written as Python state "
        "machines.",
    )
    sub = parser.add_subparsers(dest="command")

    # run (default)
    run_p = sub.add_parser("run", help="Execute a workflow (default)")
    _add_run_args(run_p)

    # test
    test_p = sub.add_parser(
        "test",
        help="Run pytest tests from a workflow's tests/ directory",
    )
    _add_test_args(test_p)

    # dot
    dot_p = sub.add_parser(
        "dot",
        help="Render a workflow graph to Graphviz DOT",
    )
    _add_dot_args(dot_p)

    # config — mirrors farrier's interface so agents.mk / scripts can call either tool
    config_p = sub.add_parser("config", help="Manage the workhorse/farrier home config")
    config_sub = config_p.add_subparsers(dest="config_command", required=True)
    # show [key] — print all keys as key=value lines, or a single bare value (farrier-compatible)
    show_p = config_sub.add_parser(
        "show", help="Print all config keys as key=value lines, or a single bare value"
    )
    show_p.add_argument(
        "key",
        nargs="?",
        default=None,
        help="If given, print only the value of this key",
    )
    # set-library / set-stablemate — write to the farrier config file (same file farrier reads)
    set_lib_p = config_sub.add_parser(
        "set-library", help="Record the prompt library directory in the home config"
    )
    set_lib_p.add_argument(
        "path", type=Path, help="Path to the library (the agents/ tree)"
    )
    set_sm_p = config_sub.add_parser(
        "set-stablemate", help="Record the stablemate checkout path in the home config"
    )
    set_sm_p.add_argument("path", type=Path, help="Path to the stablemate checkout")
    set_base_p = config_sub.add_parser(
        "set-base",
        help="Record the base library content path (for isolated/pipx installs where "
        "the stablemate-library wheel isn't importable)",
    )
    set_base_p.add_argument(
        "path", type=Path, help="Path to the base library content directory"
    )
    # list / get — workhorse-specific power/model config (workhorse's own config.toml)
    config_sub.add_parser(
        "list", help="Print the loaded workhorse config (power mappings etc.)"
    )
    get_p = config_sub.add_parser("get", help="Print one workhorse config value")
    get_p.add_argument("name", help="Config key, e.g. power or power.high.claude")

    # version
    sub.add_parser("version", help="Print the installed workhorse-agent version")

    return parser


_SUBCOMMANDS = frozenset({"run", "test", "dot", "config", "version"})


def main(
    argv: list[str] | None = None,
    *,
    workflow: str | None = None,
    registry: Registry | None = None,
) -> None:
    """The whole CLI, for every front door there is.

    ``argv`` defaults to the process arguments, so the ``workhorse`` console script
    calls this with none. ``workflow`` names the workflow up front, which is what a
    per-workflow ``workhorse-<name>`` script binds — the *only* difference between the
    two commands. There is deliberately no second parser: a per-workflow script that
    grew its own argument definitions would drift from ``workhorse run`` silently, and
    the drift would only show up as two tools that disagree about a flag.

    ``registry`` is the Python workflow the caller already holds. A
    ``Registry.main(...)`` console script is inside the distribution and so has the
    object in hand; passing it skips entry-point discovery, which means the script
    still works when the package is on ``sys.path`` without being installed."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser("workhorse" if workflow is None else f"workhorse-{workflow}")

    # Keep `workhorse --workflow ...` working: if no recognised subcommand is
    # given, inject `run` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["run"] + list(argv)

    args = parser.parse_args(argv)
    args.registry = registry
    if workflow is not None:
        _bind_workflow_name(parser, args, workflow)

    if args.command == "version":
        print(importlib.metadata.version("workhorse-agent"))
        return

    if args.command == "test":
        _run_test(args)
        return

    if args.command == "dot":
        _run_dot(args)
        return

    if args.command == "config":
        _run_config(args)
        return

    _run_run(args)


def _bind_workflow_name(
    parser: argparse.ArgumentParser, args: argparse.Namespace, name: str
) -> None:
    """Fill in the workflow a per-workflow console script already knows.

    Parsing has happened by now: this only writes the name into the slot
    ``--workflow`` would have filled, and rejects the two ways the caller can
    contradict it."""
    command = getattr(args, "command", None)
    if command not in (None, "run"):
        parser.error(
            f"'{command}' is not available here — this command runs the '{name}' "
            f"workflow. Use `workhorse {command} ...` instead."
        )
    if getattr(args, "workflow", None) is not None:
        parser.error(
            f"--workflow is not accepted here: this command always runs '{name}'."
        )
    positional = getattr(args, "positional", None) or []
    if len(positional) > 1:
        extra = " ".join(positional[1:])
        parser.error(
            f"unexpected arguments: {extra} — usage: {parser.prog} run [<flow>] [options]"
        )
    args.workflow = name


def console_script(name: str) -> Callable[..., None]:
    """Build the callable a ``workhorse-<name>`` console script points at.

    ``[project.scripts]`` targets are *called* after import, so this returns the entry
    function rather than running anything — a module-level call would fire on import
    and could not be a script target at all."""

    def entry(argv: list[str] | None = None) -> None:
        main(argv, workflow=name)

    entry.__name__ = f"workhorse_{name.replace('-', '_')}"
    entry.__qualname__ = entry.__name__
    entry.__doc__ = f"Console-script entry point for the '{name}' workflow."
    return entry


def _run_config(args: argparse.Namespace) -> None:
    try:
        _dispatch_config(args)
    except ConfigVersionError as exc:
        # A config written by a newer stablemate-core. Actionable and deterministic, so
        # it exits cleanly like every other config error here rather than as a traceback.
        raise SystemExit(f"error: {exc}") from exc


def _dispatch_config(args: argparse.Namespace) -> None:
    if args.config_command == "set-library":
        path = Path(args.path).expanduser().resolve()
        write_config_key("library_dir", str(path))
        print(f"library_dir={path}")
        return

    if args.config_command == "set-stablemate":
        path = Path(args.path).expanduser().resolve()
        write_config_key("stablemate_dir", str(path))
        print(f"stablemate_dir={path}")
        return

    if args.config_command == "set-base":
        path = Path(args.path).expanduser().resolve()
        if not _is_base_library_dir(path):
            raise SystemExit(
                f"error: {path} is not a usable base library directory — it must contain "
                "library/ or workflows/."
            )
        write_config_key("base_dir", str(path))
        print(f"base_dir={path}")
        return

    cfg = load_config()

    if args.config_command == "show":
        if args.key:
            value = cfg.get(args.key)
            if value is None:
                print(
                    f"error: '{args.key}' is not set in {config_path()}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(value)
        else:
            for key, value in cfg.items():
                print(f"{key}={value}")
        return

    if args.config_command == "list":
        print(f"# {config_path()}")
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return

    if args.config_command == "get":
        value = get_config_value(args.name, cfg)
        if value is None:
            return
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2, sort_keys=True))
        else:
            print(value)
