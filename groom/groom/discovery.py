"""Startup/refresh reconciliation: a one-shot ``docker ps -a`` + ``docker
inspect`` pass that finds every workhorse-based workflow container so a
workflow already blocked before groom started is still picked up. Steady
state comes from the in-container sidecar's push, not from repeating this
scan on a timer.

Workflow containers are identified generically — a bind mount at
``/workflow`` plus volume mounts at ``/runs`` and ``/workspace`` — matching
workhorse's own compose convention, not anything Predykt-specific.
"""

from __future__ import annotations

import json
import posixpath
from typing import Any

from . import docker_io
from .gates import AWAITING, extract_question, status_of
from .models import GateInfo, WorkflowContainer, WorkflowState

WORKFLOW_MOUNT = "/workflow"
RUNS_MOUNT = "/runs"
WORKSPACE_MOUNT = "/workspace"


def _mounts_by_dest(inspect: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m.get("Destination"): m for m in inspect.get("Mounts", []) or []}


def _env_map(inspect: dict[str, Any]) -> dict[str, str]:
    env: dict[str, str] = {}
    for kv in (inspect.get("Config") or {}).get("Env", []) or []:
        if "=" in kv:
            key, _, value = kv.partition("=")
            env[key] = value
    return env


def is_workhorse_container(inspect: dict[str, Any]) -> bool:
    mounts = _mounts_by_dest(inspect)
    return WORKFLOW_MOUNT in mounts and RUNS_MOUNT in mounts and WORKSPACE_MOUNT in mounts


def _workflow_type(inspect: dict[str, Any], mounts: dict[str, dict[str, Any]]) -> str:
    """The worker's workflow kind (``coder`` / ``author`` / …).

    workhorse mounts each workflow's definition dir at ``/workflow`` from a
    per-type source (``.../workflows/coder`` vs ``.../workflows/author``), so
    the mount source's basename is the most reliable, repo-agnostic signal.
    Fall back to the compose service name when the basename is empty or the
    generic ``workflow`` (as in a bind straight at ``…/workflow``).
    """
    source = (mounts.get(WORKFLOW_MOUNT) or {}).get("Source", "")
    wtype = posixpath.basename(source.rstrip("/"))
    if not wtype or wtype == "workflow":
        labels = (inspect.get("Config") or {}).get("Labels") or {}
        wtype = labels.get("com.docker.compose.service", "")
    return wtype


def container_from_inspect(inspect: dict[str, Any]) -> WorkflowContainer:
    mounts = _mounts_by_dest(inspect)
    env = _env_map(inspect)
    name = (inspect.get("Name") or "").lstrip("/")
    container_id = (inspect.get("Id") or "")[:12]
    running = bool((inspect.get("State") or {}).get("Running"))
    return WorkflowContainer(
        container_id=container_id,
        name=name or container_id,
        repo_name=env.get("REPO_NAME", ""),
        repo_branch=env.get("REPO_BRANCH", ""),
        workflow_type=_workflow_type(inspect, mounts),
        state=WorkflowState.RUNNING if running else WorkflowState.IDLE,
        workspace_volume=(mounts.get(WORKSPACE_MOUNT) or {}).get("Name", ""),
        runs_volume=(mounts.get(RUNS_MOUNT) or {}).get("Name", ""),
    )


def _current_run_state(runs_volume: str) -> tuple[str, str]:
    """Returns ``(current_node, terminal)`` from the most recent run
    directory's ``checkpoint.json``/``run.json``. Empty strings if the
    volume has no runs yet or its contents can't be read.
    """
    dirs = docker_io.list_run_dirs(runs_volume)
    if not dirs:
        return "", ""
    latest = dirs[-1]

    current_node = ""
    checkpoint_raw = docker_io.read_file(runs_volume, f"{latest}/checkpoint.json")
    if checkpoint_raw:
        try:
            current_node = json.loads(checkpoint_raw).get("current_id", "")
        except json.JSONDecodeError:
            pass

    terminal = ""
    run_raw = docker_io.read_file(runs_volume, f"{latest}/run.json")
    if run_raw:
        try:
            terminal = json.loads(run_raw).get("terminal") or ""
        except json.JSONDecodeError:
            pass

    return current_node, terminal


def _find_gates(workspace_volume: str) -> list[GateInfo]:
    gates = []
    for rel_path in docker_io.grep_awaiting_files(workspace_volume):
        content = docker_io.read_file(workspace_volume, rel_path)
        if content is None or status_of(content) != AWAITING:
            continue
        gates.append(GateInfo(workflow_id="", file_path=rel_path, question=extract_question(content), status=AWAITING))
    return gates


def present_container_ids() -> set[str] | None:
    """The live set of container IDs for reconciliation/prune, or ``None`` when
    docker is unreachable (so callers skip pruning rather than wipe the fleet
    on a transient outage). Not filtered to workhorse containers — a bare
    "does this id still exist" check is enough to prune vanished workers.
    """
    return docker_io.list_container_ids()


def scan() -> list[WorkflowContainer]:
    found: list[WorkflowContainer] = []
    for entry in docker_io.docker_ps_all():
        container_id = entry.get("ID", "")
        if not container_id:
            continue
        inspect = docker_io.docker_inspect(container_id)
        if not inspect or not is_workhorse_container(inspect):
            continue

        wf = container_from_inspect(inspect)

        if wf.runs_volume:
            wf.current_node, terminal = _current_run_state(wf.runs_volume)
            if terminal:
                wf.state = WorkflowState.FINISHED

        if wf.workspace_volume and wf.state != WorkflowState.FINISHED:
            for gate in _find_gates(wf.workspace_volume):
                gate.workflow_id = wf.container_id
                wf.gates[gate.file_path] = gate
            if wf.gates:
                wf.state = WorkflowState.BLOCKED

        found.append(wf)
    return found
