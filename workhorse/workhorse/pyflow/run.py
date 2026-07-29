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
            print(f"[workhorse] ERROR: {exc}")
            writer.finish(terminal="fail")
            otel.end_run("fail", error=str(exc))
            return 1
    finally:
        # A crash before any branch above finalized leaves the run marked aborted
        # rather than silently open; end_run is idempotent, so the normal paths win.
        otel.end_run("aborted", error="run aborted before finalize")

    print(f"[workhorse] done — artifacts in {writer.run_dir}")
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


def _record_interrupt(writer: ArtifactWriter) -> None:
    """Stamp an operator interrupt onto the run, attributed to the state in flight.

    Best-effort, like the YAML engine's equivalent: this runs on the way out of a
    Ctrl-C, where a second traceback would bury the resume hint.
    """
    try:
        checkpoint = writer.read_checkpoint()
    except (OSError, json.JSONDecodeError):
        checkpoint = None
    writer.record_interrupt((checkpoint or {}).get("state") or "<run>", "KeyboardInterrupt")


__all__ = ["run_pyflow"]
