"""One run of a Python state machine, from CLI arguments to an exit code.

The YAML engine's `main.run()` and this are two bodies around the same lifecycle:
resolve the run dir, set logging up, open the run's telemetry span, drive, and finalize
on every exit path — including the interrupted one, which is the path that makes a
week-long run resumable. Only the middle differs (`_step_loop` walks a graph; `drive`
calls state methods), so everything around it is kept deliberately identical rather
than reinvented: `--resume-latest` must mean one thing, and `run.json` must have the
same shape whichever engine wrote it.
"""

from __future__ import annotations

import importlib
import inspect
import os
import shutil
import sys
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse import control, gitstate, logsetup, otel, reload
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.manifest import ManifestContext
from workhorse.pyflow.driver import Resume, drive, read_resume
from workhorse.pyflow.engine import RunEnv, stub_nodes
from workhorse.pyflow.errors import PyflowError, RunBudgetExceeded, WorkflowFailed
from workhorse.pyflow.graph import preflight, registry_graphs
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.workflow import Workflow
from workhorse.records import PyflowCheckpoint, parse_checkpoint
from workhorse.references import format_missing, missing_references
from workhorse.rundir import auto_resolve, derive_run_id, runtime_deadline
from workhorse.runner import process as agent_process
from workhorse.runner import transcript
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.ladder import resolved_profile


@dataclass(frozen=True, slots=True)
class RunInvocation:
    """Everything one `workhorse-<name> run` decided, as one value.

    The fields are the CLI's contract rather than the driver's — which workflow, where
    its artifacts go, what it was given, and which of the three resume spellings the
    operator used. They travelled here as nine keyword arguments, which is a record
    whose fields were never named: every caller had to keep the list in its head, and
    a test fake mirroring the signature was the only thing keeping the two in step.

    `params` stays an untyped map on purpose. Arbitrary key→value *is* the contract —
    a workflow's own pydantic fields are what validate it, one layer further in.

    The last two fields are what the environment said, read where environments are
    read. Both default to the shipped defaults rather than to a read of their own, so
    nothing under this module reaches for `os.environ` and an in-process caller gets
    the documented values instead of whatever the shell it was launched from held.
    """

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


class _CoreReloadRequested(Exception):
    """A reload asked for workhorse itself, so the unwind must reach the process edge.

    Private, and deliberately not a `PyflowError`: nothing about the run failed, and the
    only frame allowed to act on it is the one outside the `finally` that finalizes the
    run. Its one payload is the agent CLI to come back on, because that is the single
    thing the checkpoint does *not* hold: the backend is resolved at the process edge
    from `--cli`, so a run moved onto another one has to say so in the argv it re-execs
    with. Everything else the new image needs it reads off the checkpoint, as any resume
    does.
    """

    def __init__(self, cli: str = "") -> None:
        super().__init__(cli)
        self.cli = cli


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
    # The projected keys, for the preflight below only — `missing_references` still
    # takes a render context and parses the manifest back out of it, the way a Jinja
    # helper has to. The run itself carries the value, not the projection.
    manifest_layer = invocation.context_manifest.as_context()

    # Preflight the skill/prompt references the farrier template helpers will have to
    # resolve. An unresolved one does not fail the render — it renders as prose into a
    # live agent prompt — so the only way it becomes visible is by being said out loud,
    # and the only useful moment is before the first state instead of six hours in.
    # Warned, not raised: the run is degraded, not impossible. A run carrying no
    # manifest at all is skipped, because there unresolved is the normal state.
    unresolved_refs = missing_references(registry.directory(), manifest_layer)
    if unresolved_refs:
        print(f"[workhorse] WARNING: {format_missing(unresolved_refs)}")

    if dry_run:
        # …and `--dry-run` is where that same list becomes an exit code a CI job can
        # read, alongside the static graph checks below.
        if unresolved_refs:
            print(f"[workhorse] ERROR: {format_missing(unresolved_refs)}")
            return 1
        # Static first, and it is the half that carries the weight: reading every
        # state finds the prompt that does not exist and the state nothing reaches,
        # including in the branches this run would never take. The stubbed drive
        # below then covers what only running can — imports, `setup()`, and the
        # transitions actually bound along one path.
        problems = preflight(registry_graphs(registry), registry.directory())
        if problems:
            for problem in problems:
                print(f"[workhorse] ERROR: {problem}")
            return 1
        # Its own run dir, always cleared: a dry run writes a checkpoint like any
        # other, and overwriting the checkpoint of a real week-long run — which is
        # what reusing its id would do — is not a price a smoke test may charge.
        run_id, no_cache, resume_run_dir = "dry-run", True, None

    # Before the run dir exists, because creating it is the first thing that records an
    # observation. The path is only a path: workhorse drives arbitrary workflows over
    # arbitrary trees, so nothing here claims it is a repository — `gitstate` looks, and
    # reports nothing when there is nothing to report.
    gitstate.bind(config.workspace or os.getcwd())
    otel.set_head_probe(lambda refresh: gitstate.current_head(refresh=refresh))

    writer, resume = _open_run(
        name, runs_dir, resume_run_dir, run_id=run_id, params=params, no_cache=no_cache
    )

    # Which profile the models come from, on the run rather than only in the shell history
    # that launched it. A resume with no `--profile` reads it back off this file, so a run
    # relaunched by an operator — or by a `--core` reload's own re-exec — keeps the model
    # set it was started under instead of falling back to the machine's.
    if config.profile:
        writer.record_profile(config.profile, resolved_profile(config.profile))

    # Now that there is a run dir to write into. Bound here, at the boundary, because the
    # two writers that use it are a stream callback several layers below the run and a
    # classifier that never sees a RunConfig.
    transcript.bind(
        writer.run_dir,
        enabled=config.capture_transcripts,
        max_bytes=config.transcript_max_bytes,
    )

    # A resume re-enters the flow that wrote the checkpoint. Asking for a different one
    # in the same run dir is a mistake worth naming: the checkpoint's state and params
    # belong to the flow that wrote them and mean nothing to another.
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

    try:
        wf = _instantiate(workflow_cls, resume.inputs if resume else params)
    except WorkflowFailed as exc:
        print(f"[workhorse] ERROR: {exc}")
        return 1

    env = RunEnv(
        writer=writer,
        workflow_dir=registry.directory(),
        session_id_path=writer.run_dir / ".session_id",
        config=config,
        dry_run=dry_run,
        # The composition root, handed to the run as a dependency: `self.call` runs
        # what this index holds, so a dry run is the same code path over a substituted
        # index rather than a branch inside the engine.
        nodes=stub_nodes(registry.nodes) if dry_run else registry.nodes,
        agent_stubs=registry.agent_stubs if dry_run else None,
        # The recovery ladder is the other half of that composition, and `RunEnv` builds
        # it from `config` — passing one here would be a second construction site, and
        # the one place that can bind the run's clock to it is the one that holds both.
        # Anchored to the run's ORIGINAL start, restored from run.json, so a resume
        # continues one budget rather than granting a fresh one every relaunch.
        deadline=runtime_deadline(writer.started_at, config.max_runtime_s),
        # The manifest crosses as itself, not as the keys it projects: flattening it
        # here would make every reader downstream re-derive a shape only `as_context`
        # is supposed to know.
        manifest=invocation.context_manifest,
    )

    verb = "resuming" if resume else "starting"
    print(f"[workhorse] {verb} '{name}' {workflow_cls.__name__} (run: {writer.run_dir.name})")

    # Console logging first, so a node's logger has somewhere to write even with
    # telemetry off; start_run then hangs the OTel handler off the same root logger.
    logsetup.setup()
    # Telemetry is installed here rather than at the CLI because this is where the run
    # it reports on begins and ends; what the environment said about it arrived with
    # the invocation, like every other setting.
    otel.install(invocation.telemetry)
    otel.start_run(name, writer.run_id, str(writer.run_dir))
    # From here on the run is reachable. Armed after telemetry rather than before, so the
    # first thing a cut turn does — record `reload_kill` on its own span — has somewhere
    # to land. A dry run is left unarmed: it runs no agent turn to cut, and its stubbed
    # node index would be rebuilt from a registry it never really imported.
    channel: control.ControlChannel = control.NULL_CHANNEL
    if not dry_run:
        try:
            channel = control.SocketChannel.open(writer.run_dir)
        except OSError as exc:
            # An unreachable run is worse than a run that never started only if you are
            # the operator; every other way round it is the run that matters. So this is
            # a warning and the run goes on deaf, exactly as it did before the channel.
            print(f"[workhorse] WARNING: no control channel for this run: {exc}")
        else:
            control.arm(channel)
            # How this run answers `control status`. A closure rather than a snapshot:
            # the answer worth having is where the run is *now*, and asking is usually
            # prompted by it having been somewhere too long.
            control.report_with(lambda: _status_report(name, writer))
    #: Set by the `--core` unwind below, and acted on only after the `finally` has
    #: flushed telemetry and disarmed the watch. `os.execv` runs no `finally` and no
    #: `atexit`, so exec'ing from inside the block would drop the run's last spans and
    #: leave the very dangling scope a reload exists not to produce.
    core_reload = False
    #: The agent CLI the re-exec'd image is told to use, when a `switch-cli` asked for one.
    core_reload_cli = ""
    try:
        try:
            _drive_reloadable(wf, env, resume, registry=registry, writer=writer)
        except _CoreReloadRequested as exc:
            # The engine itself was asked for, so this process image is what gets
            # replaced. Everything a clean stop does happens first — the turn was cut
            # and its span closed with the usage it accrued, the state's scope closed
            # marked, the checkpoint the state wrote on entry is on disk — and the run
            # is stamped `reload` rather than aborted, so a reader can tell the image
            # being replaced from a run that died here.
            agent_process.terminate_active()
            core_reload = True
            core_reload_cli = exc.cli
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
            # Every deliberate failure in the driver — a dead state, a bad checkpoint
            # param, an exhausted transition budget, an explicit `raise WorkflowFailed`
            # — lands here. The run dir is left resumable on purpose: these are the
            # failures an operator fixes and continues from.
            agent_process.terminate_active()
            if isinstance(exc, RunBudgetExceeded):
                # …except that "resumable" has to mean resumable *by the flag*. A
                # stamped `terminal` is what `find_latest_resumable` and the `--auto`
                # resolution read as "this run is over", so stamping one here would hide
                # the run from `--resume-latest` — the exact thing the message printed
                # below tells the operator to do. A clock that ran out is a stop, not a
                # verdict, so it is recorded the way an interrupt is: error on
                # `run.json`, no terminal, exit 1.
                print(f"[workhorse] ERROR: {exc}")
                writer.record_interrupt(_state_of(writer), str(exc))
                print(f"[workhorse] resume with: workhorse-{name} run "
                      f"--resume-run {writer.run_dir}")
                otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
                return 1
            if dry_run and isinstance(exc, WorkflowFailed) and not registry.agent_stubs:
                # …with one exception, and only while the workflow declares no
                # stand-ins. Undeclared, every agent reply is a blank model, so the
                # machine takes whichever branch a blank selects and any workflow with
                # a reachable fail terminal can be walked into one — reading that as a
                # verdict would mean no such workflow could dry-run green. A workflow
                # that declares `stub_agents({...})` has *said* what the happy path
                # answers, so reaching a fail terminal anyway is a real finding and
                # falls through to the exit-1 path below. The run dir is still marked
                # `fail` either way, because the machine really did end there; here it
                # is the *check* that passed.
                print(
                    f"[workhorse] dry-run reached the fail terminal in "
                    f"'{_state_of(writer)}': {exc}"
                )
                print("[workhorse] (nodes return stand-in values under --dry-run)")
                writer.finish(terminal="fail")
                otel.end_run("terminal")
                return 0
            print(f"[workhorse] ERROR: {exc}")
            writer.finish(terminal="fail")
            otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
            return 1
        except BackendInvocationError as exc:
            # The agent CLI failed past every rung of the ladder — most often a binary
            # that is not on the non-interactive PATH at all. The message already says
            # what to fix, so a traceback on top of it only buries the one line that
            # matters. Recorded the way a budget stop is, not stamped terminal: the
            # operator installs the CLI and resumes from the checkpoint just written.
            agent_process.terminate_active()
            print(f"[workhorse] ERROR: {exc}")
            writer.record_interrupt(_state_of(writer), str(exc))
            print(f"[workhorse] resume with: workhorse-{name} run "
                  f"--resume-run {writer.run_dir}")
            otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                         error_kind="fatal")
            return 1
        except Exception as exc:  # noqa: BLE001 — a smoke test reports, it does not raise
            # Only under `--dry-run`, and only because the stand-in values nodes
            # return there are not the values a state was written for: a body that
            # reads a field off a blank result raises something that says nothing
            # about the workflow. Name the state instead of printing a traceback
            # from inside the driver. A real run keeps propagating.
            if not dry_run:
                raise
            print(f"[workhorse] ERROR: dry-run failed in '{_state_of(writer)}': {exc!r}")
            print("[workhorse] (nodes return stand-in values under --dry-run)")
            otel.end_run("fail", error=str(exc), error_class=type(exc).__name__,
                             error_kind="fatal")
            return 1
        # Success is stamped here, *inside* the try, for the same reason every failing
        # branch above stamps before it returns: the `finally` below runs first
        # otherwise, and only the first status to arrive is kept. Stamping after it
        # recorded every successful run as `aborted` with an ERROR status — a whole
        # store of green runs that read as crashes.
        otel.end_run("terminal")
    finally:
        # A crash before any branch above finalized leaves the run marked aborted
        # rather than silently open; end_run is idempotent, so the normal paths win.
        otel.end_run("aborted", error="run aborted before finalize")
        # And the channel is closed and disarmed on every exit path: the installed one is
        # process-wide, so a run that left it armed would hand its socket to whatever ran
        # next in the same process — a second `run_pyflow` in a test, or a supervisor
        # loop. Closing also unlinks the socket, which is what makes "nobody is
        # listening" the honest answer for a run that has ended.
        control.arm(None)
        channel.close()

    if core_reload:
        return _exec_reload(name, writer.run_dir, cli=core_reload_cli)

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
    """`drive`, plus the one thing that may legitimately restart it: a live reload.

    The loop is here, at the outermost frame, because `drive` is re-entrant: a `handoff`
    runs a nested `drive` inside its parent state's body, and swapping `sys.modules`
    under a live parent frame would hand objects of the new classes to the old classes'
    pydantic validation. So the request travels as an exception until every frame is
    gone, and only then — with nothing on the stack that remembers the old modules —
    is the workflow package re-imported and the run re-entered from its checkpoint.

    Re-entry is a resume in the same process and the same run dir, which is the whole
    value: the run keeps its telemetry root span, its `run.json`, its session map and
    its wall-clock budget. It is not a new generation, and groom must not read it as one.
    """
    while True:
        try:
            return drive(wf, env, resume)
        except reload.ReloadRequested as exc:
            # What was asked for rides the exception, because the request was consumed by
            # the read that delivered it. That is the property a request file never had:
            # one request produces exactly one reload without anything having to remember
            # to clear it, so a reload onto a tree that does not import cannot become a
            # loop that re-reads the same request forever.
            # A CLI switch implies the engine: the backend is resolved once, at the
            # process edge, so re-importing the workflow package could not move a run
            # onto another agent CLI however loudly the request asked.
            core = exc.core or bool(exc.cli)
            if core:
                # `--core` means the engine itself, and no process can swap the modules
                # its own stack is executing — `drive`, the ladder and `process.py` are
                # all on this one. So the *image* is what gets replaced. The exec is not
                # taken here: it belongs on the far side of `run_pyflow`'s `finally`,
                # where the run's telemetry has been flushed and the watch disarmed.
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
                raise _CoreReloadRequested(exc.cli) from exc
            registry, replaced = _reimport(registry)
            env.workflow_dir = registry.directory()
            env.nodes = registry.nodes
            resume = _read_resume(writer.run_dir)
            # The checkpoint names its own flow, so a reload lands back in the sub-flow's
            # *parent* state and the handoff re-adopts the child checkpoint itself.
            workflow_cls = registry.class_named(resume.flow) or registry.flow(None)
            # A `WorkflowFailed` here is the honest outcome of an incompatible edit: the
            # pushed code renamed or retyped a workflow field the checkpoint still holds.
            # The run stops at a resumable checkpoint with pydantic naming the field.
            wf = _instantiate(workflow_cls, resume.inputs)
            otel.turn_event(
                "reload",
                state=resume.state,
                flow=resume.flow or "",
                core=core,
                packages=",".join(replaced),
            )
            # A log record, not a print: the reload is the one thing an operator needs
            # to see in `groom logs` when they come back to a run that changed under
            # them, and the console handler still puts it on their terminal. It names
            # the packages it replaced, because the failure this feature must never
            # have is a reload that reports success over code it did not reload — an
            # operator who fixed a library the workflow imports can read this line and
            # see whether their fix is in.
            env.log.info(
                "[workhorse] reload: re-entering '%s' on the pushed code (replaced: %s)",
                resume.state,
                ", ".join(replaced),
            )


def _exec_reload(name: str, run_dir: Path, *, cli: str = "") -> int:
    """Replace this process image with a resume of the same run. Normally never returns.

    `os.execv` rather than an exit code the caller restarts on, because exec keeps the
    pid and needs no supervisor: the same call is what reloads the engine inside a
    container and on a laptop, which is the property the whole feature is judged by. The
    argv is rebuilt rather than replayed — `run --resume-run <dir>` is the resume
    spelling, and the original one's `--param`/`--params-file` are already in the
    checkpoint, so replaying them would let a stale file win over what the run really
    holds.

    Unlike the workflow-only reload this *is* a new process, so it opens a new root span
    and a new resume generation: a `--core` reload costs the seconds between the two
    images as a resume gap, where a tier-1 reload costs nothing. That is the price named
    in the operator docs, and the reason `--core` is not the default.

    An exec that cannot happen at all — the console script moved out from under the run —
    exits with the reserved reload code instead. Under a supervisor that is a restart
    (which is also the path that picks up a *staged* core, where exec would re-run the
    image it is replacing); with no supervisor it is a nonzero exit over a run dir that
    is still resumable by hand.
    """
    argv = [sys.argv[0], "run", "--resume-run", str(run_dir)]
    if cli:
        # The one thing that is not in the checkpoint, because the backend is chosen at
        # this edge rather than held by the run. Passed explicitly rather than left to
        # the inherited environment, which still names the CLI the run started on.
        argv += ["--cli", cli]
    executable = shutil.which(argv[0]) or argv[0]
    if executable.endswith(".py"):
        # `python -m workhorse...` / a script run by path: exec the interpreter, since
        # the file itself is not required to be executable.
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
    """The top-level packages a workflow-only reload replaces, newest-code-first.

    A workflow is not one package. `workhorse_workflows` imports libraries that are
    edited in the same working tree and fixed in the same push — the doc-graph validator
    a node calls, a shared kit — and purging only the entry package would re-import the
    workflow *against the stale copies of those*, since `sys.modules` still holds them.
    The run would then report a successful reload and carry on running the code the
    operator just fixed, which is worse than not reloading at all: a no-op is visible,
    and a false receipt is not.

    So the rule is **replace the code that can be edited, keep the environment**: the
    entry flow's own package always, plus every other top-level package whose module
    file lies outside the interpreter's stdlib and site-packages — i.e. an editable or
    source-tree install, which is the only kind an operator can fix while a run holds
    it open. A wheel in site-packages is left alone, and so is the standard library.

    That line is not a heuristic about *which* packages matter; it is the safety
    invariant. Workhorse's own dependencies are environment-installed, so keeping the
    environment is what guarantees no surviving frame is left holding a class from a
    module object that has been replaced — the failure that makes a hot reload
    unpredictable rather than merely wrong. Workhorse itself is excluded by name (its
    own root, derived from this module rather than spelled), because its frames are on
    the stack doing the reload: replacing those is what `--core` is for.

    The entry package is unconditional, so a workflow installed as a wheel — the docker
    image, where nothing is a source tree — still reloads exactly as it did before.
    """
    engine = __name__.partition(".")[0]
    # `sysconfig` answers for the interpreter actually running, so inside a venv these
    # are the venv's own directories, and an editable install's `__file__` — which points
    # at the source tree, never at the `.pth` shim under site-packages — falls outside.
    env_dirs = tuple(
        Path(p).resolve()
        for p in (
            sysconfig.get_paths().get(key) for key in ("purelib", "platlib", "stdlib", "platstdlib")
        )
        if p
    )
    # Whatever is mid-execution up the stack — the console script the run was started
    # from, a caller that embedded the engine, a test driving it. Those modules match the
    # source-tree rule and must still be kept: dropping a module object whose frame is
    # still running does not stop that frame, it just guarantees the next import builds a
    # *second* copy of its classes, and the two then fail every `isinstance` between them.
    # Same reasoning as excluding the engine, arrived at by looking rather than by name.
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
            # A namespace package or a built-in: nothing on disk to have been fixed.
            continue
        path = Path(origin).resolve()
        if any(path.is_relative_to(directory) for directory in env_dirs):
            continue
        roots.append(root)
    return roots


def _reimport(registry: Registry) -> tuple[Registry, list[str]]:
    """Re-read the workflow's code from disk and return its rebuilt registry.

    What is purged is `_reloadable_roots`' answer — the entry flow's package plus every
    source-tree package alongside it — derived, not named, because workhorse is
    workflow-agnostic and must not know which distribution it is running, let alone what
    that distribution depends on. Everything under each root goes, so a fix in a node
    module, a sub-flow, or a library the nodes call is picked up alike; workhorse's own
    modules are untouched, which is the difference between this and `--core`.

    The registry is a module-level object built at import, so the fresh one is found on
    the re-imported module rather than reconstructed here — reconstructing it would mean
    this function knowing how a distribution composes its blueprints.

    Returns the registry and the roots that were replaced, which the caller logs: a
    reload the operator cannot audit is one they cannot trust.
    """
    entry = registry.entry
    if entry is None:  # pragma: no cover — a run without an entry flow never started
        raise WorkflowFailed("cannot reload a workflow that declares no entry point")
    module_name = entry.__module__
    replaced = _reloadable_roots(module_name)
    for root in replaced:
        for cached in [m for m in sys.modules if m == root or m.startswith(root + ".")]:
            del sys.modules[cached]
    # The point of a reload is that the files changed under a process that already read
    # them, which is exactly the case the finder's directory caches were built to skip.
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
    """Resolve the run directory and read back a checkpoint if there is one.

    Same rules as the YAML engine (`rundir`): an explicit `--resume-run` wins, else the
    one stable dir for this `(workflow, run-id)` is resumed in place when it holds an
    unfinished checkpoint, else it is started fresh in that same dir.
    """
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
    """What this run says about itself when asked, over the channel it was asked on.

    The state comes from the checkpoint rather than from a live variable for the same
    reason `groom` reads it: the checkpoint is the run's own account of where it is, so
    the answer cannot disagree with what a resume would do. It is re-read per request —
    a status query is rare and a stale position is the one thing this must not report.

    Everything here is already on disk, so an operator can get all of it without the run.
    What only the run can say is that it is the process *currently serving this run dir*,
    which is exactly what a reply on its own socket proves.
    """
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
    return report


def _read_resume(run_dir: Path) -> Resume:
    path = run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = parse_checkpoint(path.read_text())
    except (OSError, ValidationError) as exc:
        raise WorkflowFailed(f"cannot read checkpoint {path}: {exc}") from exc
    return read_resume(checkpoint)


def _instantiate(workflow_cls: type[Workflow], inputs: dict[str, Any]) -> Workflow:
    """Build the workflow instance from `--params` (or, on a resume, the checkpoint).

    The class's own fields ARE the parameter contract — pydantic reports a missing or
    mistyped one by name, which is the whole reason inputs are a model rather than a
    free-form dict.
    """
    try:
        return workflow_cls(**inputs)
    except ValidationError as exc:
        raise WorkflowFailed(
            f"{workflow_cls.__name__} cannot be built from the given parameters:\n{exc}"
        ) from exc


def _state_of(writer: ArtifactWriter) -> str:
    """The state the run is sitting in, read back off its checkpoint.

    Best-effort by design: every caller is already on a failure path, where a second
    exception would bury the first.
    """
    try:
        checkpoint = writer.read_checkpoint()
    except (OSError, ValidationError):
        checkpoint = None
    return checkpoint.state if isinstance(checkpoint, PyflowCheckpoint) else "<run>"


def _record_interrupt(writer: ArtifactWriter) -> None:
    """Stamp an operator interrupt onto the run, attributed to the state in flight.

    Best-effort, like the YAML engine's equivalent: this runs on the way out of a
    Ctrl-C, where a second traceback would bury the resume hint.
    """
    writer.record_interrupt(_state_of(writer), "KeyboardInterrupt")


__all__ = ["RunInvocation", "run_pyflow"]
