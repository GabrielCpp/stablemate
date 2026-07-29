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

import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse import logsetup, otel
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import Resume, drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.pyflow.errors import PyflowError, WorkflowFailed
from workhorse.pyflow.graph import preflight, registry_graphs
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.workflow import Workflow
from workhorse.rundir import auto_resolve, derive_run_id, runtime_deadline
from workhorse.runner import agent as agent_runner


def run_pyflow(
    registry: Registry,
    flow: str | None = None,
    *,
    runs_dir: Path,
    resume_run_dir: Path | None = None,
    run_id: str | None = None,
    params: dict[str, Any] | None = None,
    no_cache: bool = False,
    dry_run: bool = False,
) -> int:
    """Run one flow of `registry` and return the process exit code."""
    params = dict(params or {})
    name = registry.name or "workflow"

    if dry_run:
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

    writer, resume = _open_run(
        name, runs_dir, resume_run_dir, run_id=run_id, params=params, no_cache=no_cache
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

    config = RunConfig.from_env()
    env = RunEnv(
        writer=writer,
        workflow_dir=registry.directory(),
        session_id_path=writer.run_dir / ".session_id",
        config=config,
        dry_run=dry_run,
        # Anchored to the run's ORIGINAL start, restored from run.json, so a resume
        # continues one budget rather than granting a fresh one every relaunch.
        deadline=runtime_deadline(writer.started_at, config.max_runtime_s),
    )

    verb = "resuming" if resume else "starting"
    print(f"[workhorse] {verb} '{name}' {workflow_cls.__name__} (run: {writer.run_dir.name})")

    # Console logging first, so a node's logger has somewhere to write even with
    # telemetry off; start_run then hangs the OTel handler off the same root logger.
    logsetup.setup()
    otel.start_run(name, writer.run_id, str(writer.run_dir))
    try:
        try:
            drive(wf, env, resume)
        except KeyboardInterrupt:
            agent_runner.terminate_active()
            _record_interrupt(writer)
            print("\n[workhorse] interrupted — run paused.")
            print(f"[workhorse] resume with: workhorse --resume-run {writer.run_dir}")
            otel.end_run("interrupted", error="KeyboardInterrupt")
            raise SystemExit(130) from None
        except PyflowError as exc:
            # Every deliberate failure in the driver — a dead state, a bad checkpoint
            # param, an exhausted transition budget, an explicit `raise WorkflowFailed`
            # — lands here. The run dir is left resumable on purpose: these are the
            # failures an operator fixes and continues from.
            agent_runner.terminate_active()
            if dry_run and isinstance(exc, WorkflowFailed):
                # …with one exception. A fail terminal reached under `--dry-run` is an
                # artifact of the stand-in values, not a verdict on the workflow: every
                # agent reply is a blank model, so the machine takes whichever branch a
                # blank selects, and any workflow with a reachable fail terminal can be
                # walked into one. Report which state halted and exit 0 — the same
                # reasoning the branch below already uses to decline reading a real
                # failure into a stand-in. The run dir is still marked `fail`, because
                # the machine really did end there; it is the *check* that passed.
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
            otel.end_run("fail", error=str(exc))
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
            otel.end_run("fail", error=str(exc))
            return 1
    finally:
        # A crash before any branch above finalized leaves the run marked aborted
        # rather than silently open; end_run is idempotent, so the normal paths win.
        otel.end_run("aborted", error="run aborted before finalize")

    verdict = "dry-run ok — no node ran" if dry_run else "done"
    print(f"[workhorse] {verdict} — artifacts in {writer.run_dir}")
    otel.end_run("terminal")
    return 0


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


def _read_resume(run_dir: Path) -> Resume:
    path = run_dir / ArtifactWriter.CHECKPOINT_FILE
    try:
        checkpoint = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowFailed(f"cannot read checkpoint {path}: {exc}") from exc
    if not isinstance(checkpoint, dict):
        raise WorkflowFailed(f"checkpoint {path} is not a JSON object")
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
    except (OSError, json.JSONDecodeError):
        checkpoint = None
    return (checkpoint or {}).get("state") or "<run>"


def _record_interrupt(writer: ArtifactWriter) -> None:
    """Stamp an operator interrupt onto the run, attributed to the state in flight.

    Best-effort, like the YAML engine's equivalent: this runs on the way out of a
    Ctrl-C, where a second traceback would bury the resume hint.
    """
    writer.record_interrupt(_state_of(writer), "KeyboardInterrupt")


__all__ = ["run_pyflow"]
