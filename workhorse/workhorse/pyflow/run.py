"""One run of a Python state machine, from CLI arguments to an exit code."""

from __future__ import annotations

import importlib
import inspect
import os
import shutil
import sys
import sysconfig
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse._vendor.stablemate_core.config import CONFIG_PATH_ENV, resolve_worktree_dir
from workhorse import control, gitstate, inbox, logsetup, otel, reload
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.manifest import ManifestContext
from workhorse.pyflow.driver import Resume, drive, read_resume
from workhorse.pyflow.engine import RunEnv, stub_nodes
from workhorse.pyflow.errors import (
    AgentTurnFailed,
    PyflowError,
    RunBudgetExceeded,
    WorkflowFailed,
)
from workhorse.pyflow.graph import preflight, registry_graphs
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.workflow import Workflow
from workhorse.pyflow.worktree import WorktreeError
from workhorse.pyflow import worktree as worktree_mod
from workhorse.records import PyflowCheckpoint, parse_checkpoint
from workhorse.references import format_missing, missing_references
from workhorse.rundir import (
    auto_resolve,
    derive_run_id,
    resume_argv,
    runtime_deadline,
)
from workhorse.runner import process as agent_process
from workhorse.runner import transcript
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.ladder import resolved_profile


@dataclass(frozen=True, slots=True)
class RunInvocation:
    """Everything one `workhorse-<name> run` decided, as one value."""

    registry: Registry
    runs_dir: Path
    flow: str | None = None
    run_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    resume_run_dir: Path | None = None
    no_cache: bool = False
    dry_run: bool = False
    context_manifest: ManifestContext = field(default_factory=ManifestContext)
    config: RunConfig = field(default_factory=RunConfig)
    telemetry: otel.TelemetryHost = field(default_factory=otel.TelemetryHost)
    worktree: bool = False
    worktree_branch: str | None = None
    worktree_base: str | None = None


class _CoreReloadRequested(Exception):
    """A reload asked for workhorse itself, so the unwind must reach the process edge."""

    def __init__(self, cli: str = "", profile: str = "") -> None:
        super().__init__(cli)
        self.cli = cli
        self.profile = profile


def _dispatch_worktree(
    *,
    invocation: RunInvocation,
    writer: ArtifactWriter,
    params: dict[str, Any],
    name: str,
    dry_run: bool,
) -> int | None:
    """Fresh-dispatch worktree creation for `--worktree` (plan §§4-5, §10)."""
    repo_dir = Path(params.get("repo_dir") or Path.cwd()).resolve()
    default_branch, _ = worktree_mod.default_names(workflow=name, run_id=writer.run_id)
    branch = invocation.worktree_branch or default_branch
    sanitized_branch = branch.replace("/", "-")
    base_ref = invocation.worktree_base or "HEAD"

    worktree_dir = resolve_worktree_dir()
    if worktree_dir is None:
        print(
            "[workhorse] ERROR: --worktree requires a configured worktree_dir. "
            "Set one with `farrier config set-worktree <path>`."
        )
        return 1

    dir_name = worktree_mod.dir_name_for(repo_dir, sanitized_branch)

    if dry_run:
        print(
            f"[workhorse] --dry-run: would cut branch '{branch}' from '{base_ref}' "
            f"into worktree '{worktree_dir / dir_name}'"
        )
        return None

    try:
        cut = worktree_mod.add(
            repo_dir=repo_dir,
            worktree_dir=worktree_dir,
            branch=branch,
            base_ref=base_ref,
            dir_name=dir_name,
        )
    except WorktreeError as exc:
        print(f"[workhorse] ERROR: {exc}")
        return 1

    writer.record_worktree(str(cut.path), cut.branch)
    params["repo_dir"] = str(cut.path)
    return None


def _resume_worktree(invocation: RunInvocation, writer: ArtifactWriter, params: dict[str, Any]) -> None:
    """Resume of a worktree-dispatched run: the recorded worktree wins (plan §8)."""
    if not writer.worktree_path:
        return
    if invocation.worktree or invocation.worktree_branch or invocation.worktree_base:
        print(
            "[workhorse] --worktree ignored on resume: this run already recorded a "
            f"worktree at '{writer.worktree_path}' (branch '{writer.worktree_branch}')."
        )
    params["repo_dir"] = writer.worktree_path


def run_pyflow(invocation: RunInvocation) -> int:
    """Run one flow of the invoked registry and return the process exit code."""
    registry = invocation.registry
    runs_dir = invocation.runs_dir
    flow = invocation.flow
    run_id = invocation.run_id
    resume_run_dir = invocation.resume_run_dir
    no_cache = invocation.no_cache
    dry_run = invocation.dry_run
    params = dict(invocation.params)
    config = invocation.config
    name = registry.name or "workflow"
    manifest_layer = invocation.context_manifest.as_context()

    unresolved_refs = missing_references(registry.directory(), manifest_layer)
    if unresolved_refs:
        print(f"[workhorse] WARNING: {format_missing(unresolved_refs)}")

    if dry_run:
        if unresolved_refs:
            print(f"[workhorse] ERROR: {format_missing(unresolved_refs)}")
            return 1
        problems = preflight(registry_graphs(registry), registry.directory())
        if problems:
            for problem in problems:
                print(f"[workhorse] ERROR: {problem}")
            return 1
        run_id, no_cache, resume_run_dir = "dry-run", True, None

    gitstate.bind(config.workspace or os.getcwd())
    otel.set_repository_probe(
        lambda cwd, add_dirs, refresh: gitstate.current_scope(
            cwd, add_dirs, refresh=refresh
        ).attributes()
    )

    writer, resume = _open_run(
        name, runs_dir, resume_run_dir, run_id=run_id, params=params, no_cache=no_cache
    )

    if resume is None:
        if invocation.worktree:
            code = _dispatch_worktree(
                invocation=invocation, writer=writer, params=params, name=name, dry_run=dry_run,
            )
            if code is not None:
                return code
    else:
        _resume_worktree(invocation, writer, params)

    if config.profile:
        writer.record_profile(config.profile, resolved_profile(config.profile))

    transcript.bind(
        writer.run_dir,
        enabled=config.capture_transcripts,
        max_bytes=config.transcript_max_bytes,
    )

    workflow_cls = registry.class_named(resume.flow if resume else None)
    if workflow_cls is None:
        workflow_cls = registry.flow(flow)
    elif flow and registry.flows.get(flow) is not workflow_cls:
        print(
            f"[workhorse] ERROR: {writer.run_dir} holds a checkpoint for flow "
            f"'{workflow_cls.__name__}', but '{flow}' was requested. Resume it as it "
            "was, or start a new run (--run-id).",
        )
        return 1

    if resume:
        inputs, retired = _drop_retired_inputs(workflow_cls, resume.inputs)
        if retired:
            print(
                f"[workhorse] resume → dropping {', '.join(retired)}: "
                f"{workflow_cls.__name__} no longer declares "
                f"{'them' if len(retired) > 1 else 'it'}",
            )
    else:
        inputs = params

    try:
        wf = _instantiate(workflow_cls, inputs)
    except WorkflowFailed as exc:
        print(f"[workhorse] ERROR: {exc}")
        return 1

    env = RunEnv(
        writer=writer,
        workflow_dir=registry.directory(),
        session_id_path=writer.run_dir / ".session_id",
        config=config,
        dry_run=dry_run,
        nodes=stub_nodes(registry.nodes) if dry_run else registry.nodes,
        agent_stubs=registry.agent_stubs if dry_run else None,
        deadline=runtime_deadline(writer.started_at, config.max_runtime_s),
        manifest=invocation.context_manifest,
        worktree_dispatched=bool(writer.worktree_path),
    )

    verb = "resuming" if resume else "starting"
    print(f"[workhorse] {verb} '{name}' {workflow_cls.__name__} (run: {writer.run_dir.name})")

    logsetup.setup()
    otel.install(invocation.telemetry)
    otel.start_run(name, writer.run_id, str(writer.run_dir))
    writer.record_launch(
        [sys.executable, *sys.argv],
        resume_argv(
            sys.argv[0],
            writer.run_dir,
            cli=config.backend.name if config.backend.name != "none" else "",
            profile=config.profile,
            config_path=os.environ.get(CONFIG_PATH_ENV) or "",
        ),
        os.getcwd(),
    )
    if config.profile:
        otel.run_attribute("workhorse.profile", config.profile)
    channel: control.ControlChannel = control.NULL_CHANNEL
    if not dry_run:
        try:
            channel = control.SocketChannel.open(writer.run_dir)
        except OSError as exc:
            print(f"[workhorse] WARNING: no control channel for this run: {exc}")
        else:
            control.arm(channel)
            control.report_with(lambda: _status_report(name, writer))
    core_reload = False
    core_reload_cli = ""
    core_reload_profile = ""
    try:
        try:
            _drive_reloadable(wf, env, resume, registry=registry, writer=writer)
        except _CoreReloadRequested as exc:
            agent_process.terminate_active()
            core_reload = True
            core_reload_cli = exc.cli
            core_reload_profile = exc.profile
            otel.end_run("reload")
        except KeyboardInterrupt:
            agent_process.terminate_active()
            _record_interrupt(writer)
            print("\n[workhorse] interrupted — run paused.")
            print(f"[workhorse] resume with: workhorse-{name} run "
                  f"--resume-run {writer.run_dir}")
            otel.end_run("interrupted", error="KeyboardInterrupt",
                         error_class="KeyboardInterrupt", error_kind="interrupt")
            raise SystemExit(130) from None
        except PyflowError as exc:
            agent_process.terminate_active()
            if isinstance(exc, RunBudgetExceeded | AgentTurnFailed):
                print(f"[workhorse] ERROR: {exc}")
                writer.record_interrupt(_state_of(writer), str(exc))
                print(f"[workhorse] resume with: workhorse-{name} run "
                      f"--resume-run {writer.run_dir}")
                otel.end_run("interrupted", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
                return 1
            if dry_run and isinstance(exc, WorkflowFailed) and not registry.agent_stubs:
                print(
                    f"[workhorse] dry-run reached the fail terminal in "
                    f"'{_state_of(writer)}': {exc}"
                )
                print("[workhorse] (nodes return stand-in values under --dry-run)")
                writer.finish(terminal="fail")
                otel.end_run("terminal")
                return 0
            print(f"[workhorse] ERROR: {exc}")
            _record_failure_handoff(writer, exc)
            writer.finish(terminal="fail")
            otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
            return 1
        except BackendInvocationError as exc:
            agent_process.terminate_active()
            print(f"[workhorse] ERROR: {exc}")
            writer.record_interrupt(_state_of(writer), str(exc))
            print(f"[workhorse] resume with: workhorse-{name} run "
                  f"--resume-run {writer.run_dir}")
            otel.end_run("interrupted", error=str(exc), error_class=type(exc).__name__,
                         error_kind="fatal")
            return 1
        except Exception as exc:  # noqa: BLE001 — a smoke test reports, it does not raise
            if not dry_run:
                raise
            print(f"[workhorse] ERROR: dry-run failed in '{_state_of(writer)}': {exc!r}")
            print("[workhorse] (nodes return stand-in values under --dry-run)")
            otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
            return 1
        otel.end_run("terminal")
    finally:
        otel.end_run("aborted", error="run aborted before finalize")
        control.arm(None)
        channel.close()

    if core_reload:
        return _exec_reload(
            name, writer.run_dir, cli=core_reload_cli, profile=core_reload_profile
        )

    verdict = "dry-run ok — every node ran its stand-in" if dry_run else "done"
    print(f"[workhorse] {verdict} — artifacts in {writer.run_dir}")
    return 0


def _drive_reloadable(
    wf: Workflow,
    env: RunEnv,
    resume: Resume | None,
    *,
    registry: Registry,
    writer: ArtifactWriter,
) -> Any:
    """`drive`, plus the one thing that may legitimately restart it: a live reload."""
    while True:
        try:
            return drive(wf, env, resume)
        except reload.ReloadRequested as exc:
            core = exc.core or bool(exc.cli)
            if core:
                pending_resume = _read_resume(writer.run_dir)
                otel.turn_event(
                    "reload",
                    state=pending_resume.state,
                    flow=pending_resume.flow or "",
                    core=True,
                    cli=exc.cli,
                )
                env.log.info(
                    "[workhorse] reload: --core — re-executing this run from '%s'",
                    pending_resume.state,
                )
                live = env.agent_runner.profile.name if env.agent_runner else ""
                backend = env.config.backend.name
                raise _CoreReloadRequested(
                    exc.cli or (backend if backend != "none" else ""),
                    live if live != env.config.profile else "",
                ) from exc
            registry, replaced = _reimport(registry)
            env.workflow_dir = registry.directory()
            env.nodes = registry.nodes
            resume = _read_resume(writer.run_dir)
            workflow_cls = registry.class_named(resume.flow) or registry.flow(None)
            inputs, retired = _drop_retired_inputs(workflow_cls, resume.inputs)
            if retired:
                env.log.info(
                    "[workhorse] reload: dropping %s — %s no longer declares %s",
                    ", ".join(retired),
                    workflow_cls.__name__,
                    "them" if len(retired) > 1 else "it",
                )
            wf = _instantiate(workflow_cls, inputs)
            otel.turn_event(
                "reload",
                state=resume.state,
                flow=resume.flow or "",
                core=core,
                packages=",".join(replaced),
            )
            env.log.info(
                "[workhorse] reload: re-entering '%s' on the pushed code (replaced: %s)",
                resume.state,
                ", ".join(replaced),
            )


def _exec_reload(name: str, run_dir: Path, *, cli: str = "", profile: str = "") -> int:
    """Replace this process image with a resume of the same run."""
    argv = resume_argv(
        sys.argv[0],
        run_dir,
        cli=cli,
        profile=profile,
        config_path=os.environ.get(CONFIG_PATH_ENV) or "",
    )
    executable = shutil.which(argv[0]) or argv[0]
    if executable.endswith(".py"):
        argv, executable = [sys.executable, *argv], sys.executable
    print(f"[workhorse] reload: re-executing {' '.join(argv)}")
    try:
        os.execv(executable, argv)
    except OSError as exc:
        print(
            f"[workhorse] ERROR: reload --core could not re-execute {executable}: {exc}"
        )
        print(f"[workhorse] resume with: workhorse-{name} run --resume-run {run_dir}")
    return reload.RELOAD_EXIT_CODE


def _reloadable_roots(entry_module: str) -> list[str]:
    """The top-level packages a workflow-only reload replaces, newest-code-first."""
    engine = __name__.partition(".")[0]
    env_dirs = tuple(
        Path(p).resolve()
        for p in (
            sysconfig.get_paths().get(key) for key in ("purelib", "platlib", "stdlib", "platstdlib")
        )
        if p
    )
    live = set()
    frame = inspect.currentframe()
    while frame is not None:
        live.add(str(frame.f_globals.get("__name__", "")).partition(".")[0])
        frame = frame.f_back

    roots = [entry_module.partition(".")[0]]
    for name, module in list(sys.modules.items()):
        root = name.partition(".")[0]
        if root in roots or root == engine or root in live:
            continue
        if root in sys.stdlib_module_names:
            continue
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        path = Path(origin).resolve()
        if any(path.is_relative_to(directory) for directory in env_dirs):
            continue
        roots.append(root)
    return roots


def _reimport(registry: Registry) -> tuple[Registry, list[str]]:
    """Re-read the workflow's code from disk and return its rebuilt registry."""
    entry = registry.entry
    if entry is None:  # pragma: no cover — a run without an entry flow never started
        raise WorkflowFailed("cannot reload a workflow that declares no entry point")
    module_name = registry.module or entry.__module__
    replaced = _reloadable_roots(module_name)
    for root in replaced:
        for cached in [m for m in sys.modules if m == root or m.startswith(root + ".")]:
            del sys.modules[cached]
    importlib.invalidate_caches()
    module = importlib.import_module(module_name)
    for value in vars(module).values():
        if isinstance(value, Registry) and value.name == registry.name and value.entry:
            return value, replaced
    raise WorkflowFailed(
        f"reloaded {module_name} but found no Registry({registry.name!r}) on it, so the "
        "run would carry on against the code it was asked to replace. Resume the run to "
        "pick the new code up."
    )


def _open_run(
    name: str,
    runs_dir: Path,
    resume_run_dir: Path | None,
    *,
    run_id: str | None,
    params: dict[str, Any],
    no_cache: bool,
) -> tuple[ArtifactWriter, Resume | None]:
    """Resolve the run directory and read back a checkpoint if there is one."""
    if resume_run_dir is not None:
        return ArtifactWriter.resume(resume_run_dir), _read_resume(resume_run_dir)

    rid, existing = auto_resolve(runs_dir, name, derive_run_id(run_id, params))
    if no_cache and existing is not None:
        shutil.rmtree(existing, ignore_errors=True)
        existing = None
    if existing is not None:
        return ArtifactWriter.resume(existing), _read_resume(existing)
    return ArtifactWriter(name, runs_dir, run_id=rid), None


def _status_report(name: str, writer: ArtifactWriter) -> dict[str, object]:
    """What this run says about itself when asked, over the channel it was asked on."""
    report: dict[str, object] = {
        "attached": True,
        "workflow": name,
        "run": writer.run_id,
        "run_dir": str(writer.run_dir),
        "pid": os.getpid(),
    }
    try:
        checkpoint = parse_checkpoint((writer.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    except (OSError, ValidationError) as exc:
        report["state"] = f"no readable checkpoint yet ({exc.__class__.__name__})"
        return report
    if not isinstance(checkpoint, PyflowCheckpoint):
        report["state"] = "a checkpoint from the retired YAML engine"
        return report
    report["state"] = checkpoint.state
    report["flow"] = checkpoint.flow or ""
    report["seq"] = checkpoint.seq
    report["waiting_on"] = checkpoint.waiting_on or ""
    return report


def _read_resume(run_dir: Path) -> Resume:
    path = run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = parse_checkpoint(path.read_text())
    except (OSError, ValidationError) as exc:
        raise WorkflowFailed(f"cannot read checkpoint {path}: {exc}") from exc
    return read_resume(checkpoint)


def _instantiate(workflow_cls: type[Workflow], inputs: dict[str, Any]) -> Workflow:
    """Build the workflow instance from `--params` (or, on a resume, the checkpoint)."""
    try:
        return workflow_cls(**inputs)
    except ValidationError as exc:
        raise WorkflowFailed(
            f"{workflow_cls.__name__} cannot be built from the given parameters:\n{exc}"
        ) from exc


def _drop_retired_inputs(
    workflow_cls: type[Workflow], inputs: dict[str, Any]
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Strip stored inputs naming a field the workflow no longer declares."""
    retired = tuple(sorted(set(inputs) - set(workflow_cls.model_fields)))
    if not retired:
        return inputs, ()
    return {k: v for k, v in inputs.items() if k not in retired}, retired


def _state_of(writer: ArtifactWriter) -> str:
    """The state the run is sitting in, read back off its checkpoint."""
    try:
        checkpoint = writer.read_checkpoint()
    except (OSError, ValidationError):
        checkpoint = None
    return checkpoint.state if isinstance(checkpoint, PyflowCheckpoint) else "<run>"


def _record_interrupt(writer: ArtifactWriter) -> None:
    """Stamp an operator interrupt onto the run, attributed to the state in flight."""
    writer.record_interrupt(_state_of(writer), "KeyboardInterrupt")


def _record_failure_handoff(writer: ArtifactWriter, exc: PyflowError) -> None:
    """Diagnose the stop into the run's outbox, so it reaches whoever is watching it."""
    state = _state_of(writer)
    failure_class = getattr(exc, "failure_class", "") or type(exc).__name__
    lines = [
        f"failure_class: {failure_class}",
        f"node: {state}",
        f"error: {exc}",
        f"run_dir: {writer.run_dir}",
        f"checkpoint: {writer.run_dir / ArtifactWriter.CHECKPOINT_FILE}",
        f"turns: {writer.run_dir / ArtifactWriter.TURNS_DIR}",
    ]
    for name, path in getattr(exc, "artifacts", {}).items():
        lines.append(f"{name}: {path}")
    body = "\n".join(lines)
    try:
        inbox.append(
            writer.run_dir / "inbox.jsonl",
            id=uuid.uuid4().hex,
            body=body,
            at=datetime.now(timezone.utc).isoformat(),
            kind="failure",
        )
    except Exception as inbox_exc:  # noqa: BLE001 — diagnosis must not bury the failure
        print(f"[workhorse] WARNING: could not write failure handoff to outbox: {inbox_exc}")


__all__ = ["RunInvocation", "run_pyflow"]
