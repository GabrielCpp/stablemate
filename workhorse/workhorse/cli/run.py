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
from typing import Any

from pydantic import ValidationError

from workhorse import otel
from workhorse._vendor.stablemate_core.config import (
    CONFIG_PATH_ENV,
    DEFAULT_CLI_KEY,
    UnknownProfileError,
    config_path,
    get_config_value,
    load_config,
    profile_backends,
    profile_has_backend,
    resolve_default_cli,
    select_profile,
)
from workhorse.cli.params import load_params
from workhorse.config_run import RunConfig
# Bound under its historical private name, which is also what lets a test patch the
# loader on this module and have the CLI see it.
from workhorse.manifest import load_context_manifest as _load_context_manifest
from workhorse.packaged import PackagedWorkflowError
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.records import parse_run_record
# Re-imported under its historical private name: the run-identity rules live in
# `rundir` so the driver can obey them without importing this module.
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
        "native backend (cline/opencode) and give nodes an 'openrouter/<slug>' model.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help="Resolve this run's models from the config's [profiles.<NAME>] tables "
        "instead of its top-level ones. A profile REPLACES them — nothing outside it "
        "is inherited — and is independent of --cli, which chooses whose entries in it "
        "apply. Its `default_cli` is only the default value of --cli.",
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
        "--on-fail",
        default=None,
        metavar="COMMAND",
        help="Shell command to run if this run ends FAILED. Overrides "
        "$WORKHORSE_ON_FAIL. Spawned detached with the failure in its environment "
        "($WORKHORSE_RUN_ID, _RUN_DIR, _WORKFLOW, _REPO, _NODE, _ERROR, _ERROR_CLASS, "
        "_RESUME_CMD) — it cannot delay or fail the run, and $WORKHORSE_ON_FAIL is "
        "stripped from it so a hook that starts another run cannot recurse.",
    )
    parser.add_argument(
        "--on-fail-pid",
        default=None,
        type=int,
        metavar="PID",
        help="Print the failure on the terminal this PID is attached to, instead of "
        "(or as well as) --on-fail. Overrides $WORKHORSE_ON_FAIL_PID. Use it to be "
        "told in a shell you already have open — including over SSH, where a hook "
        "that opens a window has nowhere to open it. It WRITES to that terminal; it "
        "cannot type into whatever is running there.",
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

    _apply_config_path(getattr(args, "config", None))

    # The consuming repo is the directory workhorse is launched in — same <cwd> rule
    # as the runs-dir default below. Pin AGENT_REPO_DIR to the launch dir when the
    # caller hasn't set it, so every *subprocess* (the agent CLI and whatever it
    # shells out to) agrees on the repo without needing the farrier Makefile.
    #
    # The workflow itself does not read it: this is the boundary, and what crosses it
    # is `repo_dir`, resolved below and handed over as a run parameter.
    os.environ.setdefault("AGENT_REPO_DIR", str(Path.cwd().resolve()))

    # --cli (else AGENT_CLI, else the config's `default_cli`, else claude) selects the
    # backend for the run. The resolved name is written back to AGENT_CLI so the whole
    # process — and every agent subprocess it spawns — reads one answer: the manifest
    # and template layers ask the environment for the active CLI at their own edges,
    # and a config default that only `get_backend` knew about would have them
    # projecting a Claude manifest for an opencode run.
    # The profile is selected before the CLI is, because it holds one rung of the
    # ladder: --cli > AGENT_CLI > the profile's default_cli > the top-level one > claude.
    # The two are independent axes — the profile holds a mapping keyed by backend, and
    # --cli chooses whose entries in it apply — so a profile can carry a default without
    # dictating the backend.
    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (Path.cwd() / ".agents" / "runs").resolve()
    # Resolved before the profile below, and only because the profile may come *from* it:
    # a run being resumed already chose a model set, and the flag it chose with is not on
    # this command line.
    resume_run_dir = _resume_run_dir(args, runs_dir, registry.name)

    profile_name = (getattr(args, "profile", None) or "").strip()
    if not profile_name and resume_run_dir is not None:
        profile_name = _recorded_profile(resume_run_dir)
    cfg = load_config()
    try:
        profile = select_profile(cfg, profile_name)
    except UnknownProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    resolved_cli = (
        args.cli or os.environ.get("AGENT_CLI") or _configured_default_cli(cfg, profile)
    ).strip().lower()
    os.environ["AGENT_CLI"] = resolved_cli

    # Resolve the active backend now so an unknown name fails fast with a clear
    # message instead of mid-run — and because this is the ring that gets to know
    # adapters exist. What travels on the invocation is the adapter itself, so
    # nothing further in has to reach back to the registry to find one.
    try:
        backend = get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    _check_profile_resolves(profile_name, profile, backend.name)

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
        resume_run_dir=resume_run_dir,
        no_cache=getattr(args, "no_cache", False),
        dry_run=getattr(args, "dry_run", False),
        context_manifest=_load_context_manifest(args.context_file),
        # Read last, after `--cli` and the repo-dir default above have had their say,
        # so what the run is given is the environment as the CLI finally settled it.
        config=replace(
            RunConfig.from_env(os.environ),
            backend=backend,
            profile=profile_name,
            **_on_fail_overrides(args),
        ),
        telemetry=otel.TelemetryHost(otel.OtelSettings.from_env(os.environ)),
    )


def _on_fail_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """The failure-notification flags, as `replace` kwargs — only the ones actually given.

    An absent flag is left out of the dict entirely rather than passed as its default,
    so `--on-fail` unset means "whatever $WORKHORSE_ON_FAIL said" and not "nothing". The
    distinction is the whole point of the ladder: the env var is how a supervisor arms
    every run it launches, and a flag the operator did not type must not disarm it.
    """
    overrides: dict[str, Any] = {}
    if args.on_fail is not None:
        overrides["on_fail"] = args.on_fail.strip()
    if args.on_fail_pid is not None:
        overrides["on_fail_pid"] = max(0, args.on_fail_pid)
    return overrides


def _configured_default_cli(cfg: dict[str, Any], profile: dict[str, Any]) -> str:
    """The file-sourced rungs of the CLI ladder: the profile's `default_cli`, then the
    top-level one, then the built-in.

    Two calls rather than one because `resolve_default_cli` answers with the built-in
    when it finds nothing — which cannot be told from a profile that really says
    `default_cli = "claude"`. Asking for the raw key first is what keeps a profile that
    names no CLI from erasing the machine's answer.
    """
    named = get_config_value(DEFAULT_CLI_KEY, profile)
    if isinstance(named, str) and named.strip():
        return resolve_default_cli(profile)
    return resolve_default_cli(cfg)


def _check_profile_resolves(name: str, profile: dict[str, Any], backend: str) -> None:
    """Refuse a selected profile that cannot map a model for the backend in play.

    Both failures below resolve to an empty mapping at every node and are therefore
    invisible: the run does not fail, it spends however many days it has on the harness's
    own default model. That is precisely the "typo found at hour 30" `--dry-run` exists
    for, so these run before the first state on a dry run too.

    An otherwise-empty profile that carries only `default_cli` stays legal — it selects a
    CLI and claims nothing about models, which is a coherent thing to want.
    """
    if not name:
        return
    consulted = f"(in {config_path()})"

    unknown = [n for n in profile_backends(profile) if n not in backend_names()]
    if unknown:
        print(
            f"error: profile {name!r} keys models by unknown CLI backend(s) "
            f"{', '.join(repr(n) for n in unknown)} {consulted}; known backends are: "
            f"{', '.join(backend_names())}",
            file=sys.stderr,
        )
        sys.exit(1)

    carries_models = bool(profile.get("power")) or bool(profile.get("default"))
    if carries_models and not profile_has_backend(profile, backend):
        print(
            f"error: profile {name!r} has no entries for CLI backend {backend!r} "
            f"{consulted}; it maps: {', '.join(profile_backends(profile)) or 'nothing'}. "
            f"--profile and --cli are independent axes — pick a backend the profile "
            f"maps, or give the profile a [power.<tier>.default] fallback.",
            file=sys.stderr,
        )
        sys.exit(1)


def _apply_config_path(raw: str | None) -> None:
    """Point the whole process at the config `--config` named, or leave discovery alone.

    Written back into $STABLEMATE_CONFIG rather than carried on the invocation, exactly
    as `--cli` is written back into $AGENT_CLI, and for the same reason: the config is
    re-read per node and by every subprocess this run spawns, each through its own
    `config_path()`. A flag that only reached the resolver here would name one file while
    the per-node re-read named another — a divergence with no visible symptom.

    Nothing is written back when the flag is absent: stamping the *discovered* path would
    make it explicit, and an explicitly named path suppresses the legacy per-tool merge in
    `load_config` — so a machine still on the pre-unification files would silently lose
    them to a flag nobody passed.

    A path that is not a file is refused here rather than read as an empty config. `run`
    is the boundary where failing is safe, and the alternative is a week-long run on
    default models because the file was named with a typo.
    """
    if not raw:
        return
    path = Path(raw).expanduser()
    if not path.is_file():
        print(f"error: --config {raw}: no such file", file=sys.stderr)
        sys.exit(1)
    os.environ[CONFIG_PATH_ENV] = str(path.resolve())


def _recorded_profile(run_dir: Path) -> str:
    """The profile a run was started under, read back off its `run.json`.

    A resume is a continuation, not a new decision: the operator who typed `--profile
    cheap` a week ago is rarely the one typing `--resume-run` now, and re-resolving the
    same nodes against the machine's global model set is a substitution nothing in the
    output would show. So the recorded name is re-applied unless this command line names
    one, which overrides it — that being the only way to *move* a run onto another set.
    It is also what carries a run's models across a `switch-cli`, whose re-exec is exactly
    this flagless resume.

    Best-effort: a run dir with no readable record simply has no profile to re-apply, and
    the run proceeds on the top-level tables as it always did.
    """
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
