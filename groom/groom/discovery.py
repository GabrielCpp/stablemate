"""Startup/refresh reconciliation: a one-shot ``docker ps -a`` + ``docker
inspect`` pass that finds every workhorse-based workflow container so a
workflow already blocked before groom started is still picked up. Steady
state comes from the in-container sidecar's push, not from repeating this
scan on a timer.

Workflow containers are identified generically — a ``WORKFLOW`` in the
environment plus mounts at ``/runs`` and ``/workspace`` — matching workhorse's
own compose convention, not anything repo-specific.

That used to require a bind at ``/workflow`` as well, which matched **nothing**:
a workflow stopped being a directory of yaml handed to a generic runner and
became an installed distribution with its own console script, so workhorse's
compose deliberately mounts no such path. Every container failed the test, and
containers reached the dashboard only via the sidecar's ``hello`` — meaning a
container whose sidecar never came up was invisible. ``$WORKFLOW`` is the
signal that replaced it: it is what the container is *told to run*, so it also
names the workflow type without inferring it from a mount's basename.
"""

from __future__ import annotations

import json
import posixpath
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from groom import docker_io
from groom.gates import AWAITING, extract_question, status_of
from groom.models import GateInfo, WorkflowContainer, WorkflowState

# Cap on concurrent per-container docker calls during a scan. The work is
# I/O-bound subprocess (docker inspect + exec), so a small pool collapses total
# wall time to ~the slowest single container without hammering the daemon.
_SCAN_WORKERS = 8

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
    """A container running a workhorse workflow: told which one, and with somewhere
    to put its artifacts and its working tree."""
    mounts = _mounts_by_dest(inspect)
    if RUNS_MOUNT not in mounts or WORKSPACE_MOUNT not in mounts:
        return False
    return bool(_env_map(inspect).get("WORKFLOW"))


def _workflow_type(inspect: dict[str, Any], mounts: dict[str, dict[str, Any]]) -> str:
    """The worker's workflow kind (``coder`` / ``author`` / …).

    ``$WORKFLOW`` is what the container was told to run, and the entrypoint spawns
    that name's console script — so it is the workflow type by construction, not an
    inference. The legacy ``/workflow`` mount basename is still read for a container
    launched by an older harness, and the compose service name is the last resort.
    """
    wtype = _env_map(inspect).get("WORKFLOW", "")
    if not wtype:
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
        # Baked into the container config at create time, so a row discovered by a
        # scan joins to the same telemetry as one built from a sidecar hello.
        run_id=env.get("AGENT_RUN_ID", ""),
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


def _apply_snapshot(wf: WorkflowContainer, snapshot: dict[str, Any]) -> None:
    """Fold a sidecar ``--query`` snapshot into a workflow: current node, then
    terminal-wins-over-gates (a finished run has no live gate to answer)."""
    wf.current_node = snapshot.get("current_node") or wf.current_node
    if snapshot.get("terminal"):
        wf.state = WorkflowState.FINISHED
        return
    for gate in snapshot.get("gates") or []:
        file_path = gate.get("file_path", "")
        if not file_path:
            continue
        wf.gates[file_path] = GateInfo(
            workflow_id=wf.container_id,
            file_path=file_path,
            question=gate.get("question", ""),
            status=AWAITING,
        )
    if wf.gates:
        wf.state = WorkflowState.BLOCKED


def _resolve_via_volumes(wf: WorkflowContainer) -> None:
    """The original throwaway-container path: reconstruct run node + gates by
    reading the named volumes. Used for stopped containers (can't ``exec``) and
    as the fallback when a running container's sidecar query fails."""
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


def _resolve_container(container_id: str) -> WorkflowContainer | None:
    """Inspect one container and, if it's a workhorse workflow, resolve its
    state — preferring the in-container sidecar query for running containers and
    falling back to volume reads for stopped/legacy ones. Returns ``None`` for
    non-workflow containers so they're dropped from the scan."""
    inspect = docker_io.docker_inspect(container_id)
    if not inspect or not is_workhorse_container(inspect):
        return None

    wf = container_from_inspect(inspect)
    running = bool((inspect.get("State") or {}).get("Running"))
    snapshot = docker_io.sidecar_query(wf.container_id) if running else None
    if snapshot is not None:
        _apply_snapshot(wf, snapshot)
    else:
        _resolve_via_volumes(wf)
    return wf


def scan() -> list[WorkflowContainer]:
    ids = [entry.get("ID", "") for entry in docker_io.docker_ps_all() if entry.get("ID")]
    if not ids:
        return []
    # Preserve docker-ps order (pool.map is ordered) for a stable UI/tests.
    with ThreadPoolExecutor(max_workers=min(_SCAN_WORKERS, len(ids))) as pool:
        resolved = pool.map(_resolve_container, ids)
    return [wf for wf in resolved if wf is not None]
