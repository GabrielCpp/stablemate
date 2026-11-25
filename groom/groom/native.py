from __future__ import annotations

import asyncio
import logging
import os

from watchfiles import DefaultFilter, awatch

from groom import (
    alerting,
    alerts,
    discovery,
    docker_io,
    live,
    live_transcript,
    localfs,
    norms,
    pools,
    projection,
    sidecar_hub,
    state,
    store,
    tasks,
)
from groom.gate_backfill import _ensure_gate_backfill
from groom.live_history import LiveHistory
from groom.models import (
    GateInfo,
    RunTelemetry,
    WorkflowContainer,
    WorkflowState,
)
from groom.native_attend import _attend_gates
from groom.native_figures import _figures_rev

logger = logging.getLogger(__name__)


TRANSCRIPT_POLL_S = float(os.environ.get("GROOM_TRANSCRIPT_POLL_S", "0.5"))


SERVED_BY_SIDECAR = "sidecar"


SERVED_BY_VOLUME = "volume"


SERVED_BY_HOST = "host"


def _all_workflows() -> list:
    return list(state.WORKFLOWS.values())


_NORM_TASKS: set[asyncio.Task] = set()


async def _read_norms(container_id: str, workflow: str, node: str) -> None:
    """Read one node's norms through the query pool, then push the watching tabs when they changed."""
    if await norms.refresh(workflow, node):
        live.mark_run(container_id)


def _queue_norms(wf: WorkflowContainer, tel: RunTelemetry | None) -> None:
    """Queue a norm read when the run's node has none cached or the run just moved to it. A render never waits on the read."""
    node = tel.current_node if tel else wf.current_node
    workflow = projection.run_workflow(wf, tel)
    if not norms.needs_read(projection.run_id_of(wf), workflow, node):
        return
    task = tasks.spawn(_read_norms(wf.container_id, workflow, node), name="read-norms")
    _NORM_TASKS.add(task)
    task.add_done_callback(_NORM_TASKS.discard)


def _stamp_revisions(detail: dict, wf: WorkflowContainer) -> None:
    """Add the revisions a pane follows: the Overview's figures, and the Activity and Raw feeds. A run with no history reports 0."""
    history = state.HISTORIES.get(projection.run_id_of(wf))
    detail["figures_rev"] = _figures_rev(wf)
    detail["activity_rev"] = history.activity_rev if history is not None else 0
    detail["metrics_rev"] = history.metrics_rev if history is not None else 0
    detail["workspace_rev"] = wf.workspace_rev


async def _detail_message(wf: WorkflowContainer) -> dict:
    """One run's detail pane, addressed to the tabs watching that run."""
    tel, facts, logs, history = await _run_facts(wf)
    _queue_norms(wf, tel)
    message = projection.detail_message(wf, tel, facts, logs, history=history)
    _stamp_revisions(message["detail"], wf)
    return message


live.use_detail_builder(_detail_message)


def _native_run_dir(wf: WorkflowContainer) -> str:
    """Where a native run's transcripts live on groom's own host, or empty for a container run."""
    return wf.runs_volume if wf.native else ""


async def _tail_transcript(wf: WorkflowContainer) -> None:
    """Read the new complete transcript lines of a native run whose pane is open into its history, and mark the run when lines arrived, whoever asked for the read."""
    run_dir = _native_run_dir(wf)
    history = state.HISTORIES.get(projection.run_id_of(wf))
    if not run_dir or history is None or not history.loaded:
        return
    async with state.HISTORY_LOCK:
        before = history.activity_rev
        await asyncio.to_thread(live_transcript.poll, history, run_dir)
        arrived = history.activity_rev != before
    if arrived:
        live.mark_run(wf.container_id)


_TRANSCRIPT_FILTER = DefaultFilter()


async def _follow_transcript(wf: WorkflowContainer) -> None:
    """Read a watched native run's new transcript lines the moment a transcript file changes, and every ``TRANSCRIPT_POLL_S`` once the system refuses or drops the file watch, until the last tab leaves."""
    run_dir = _native_run_dir(wf)
    marker = f"{os.sep}transcripts{os.sep}"
    try:
        async for changes in awatch(run_dir, watch_filter=_TRANSCRIPT_FILTER, debounce=100, step=50):
            if not any(marker in path for _, path in changes):
                continue
            await _tail_transcript(wf)
    except Exception:  # noqa: BLE001 - a run whose files cannot be watched is still followed by reading them
        logger.error("groom: no file watch for %s, reading its transcript every %s s", wf.container_id, TRANSCRIPT_POLL_S, exc_info=True)
    while True:
        await asyncio.sleep(TRANSCRIPT_POLL_S)
        try:
            await _tail_transcript(wf)
        except Exception:  # noqa: BLE001 - one failed read must not end the follow
            logger.exception("transcript read failed for %s", wf.container_id)


def _watch_transcript(wf: WorkflowContainer) -> None:
    key = projection.run_id_of(wf)
    task = state.TRANSCRIPT_TASKS.get(key)
    if task is not None and not task.done():
        return
    if not _native_run_dir(wf):
        return
    state.TRANSCRIPT_TASKS[key] = tasks.spawn(_follow_transcript(wf), name="follow-transcript")


_TAILS: dict[str, dict[str, bool]] = {}


_TAIL_RUNS: dict[str, str] = {}


_TAIL_TASKS: set[asyncio.Task] = set()


async def _tail_until_quiet(container_id: str) -> None:
    """Tail one container's transcript and push its pane, again for as long as new announcements arrive meanwhile."""
    flags = _TAILS[container_id]
    try:
        while True:
            wf = state.WORKFLOWS.get(container_id)
            conn = sidecar_hub.get(container_id)
            history = state.HISTORIES.get(projection.run_id_of(wf)) if wf is not None else None
            if conn is not None and history is not None and history.loaded:
                await live_transcript.tail(conn, history, _TAIL_RUNS.get(container_id, ""))
            live.mark_run(container_id)
            if not flags["again"]:
                return
            flags["again"] = False
    except Exception:  # noqa: BLE001 - a pane that missed a transcript pass is not a broken groom
        logger.exception("transcript tail failed for %s", container_id)
    finally:
        _TAILS.pop(container_id, None)


def _schedule_tail(container_id: str) -> None:
    """Ask for a container transcript pass without waiting for it; an unwatched container is skipped."""
    if not state.watchers_of(container_id):
        return
    flags = _TAILS.get(container_id)
    if flags is not None:
        flags["again"] = True
        return
    _TAILS[container_id] = {"again": False}
    task = tasks.spawn(_tail_until_quiet(container_id), name="tail-transcript")
    _TAIL_TASKS.add(task)
    task.add_done_callback(_TAIL_TASKS.discard)


async def _ensure_volumes(container_id: str) -> None:
    """Fill in the workspace/runs volume names for a container we've only heard about via a sidecar push so far (pushes carry no docker-level metadata — only what the container's own env exposes)."""
    wf = state.WORKFLOWS.get(container_id)
    if wf and wf.native:
        return
    if wf and wf.workspace_volume:
        return
    inspect = await asyncio.to_thread(docker_io.docker_inspect, container_id)
    if not inspect:
        return
    found = discovery.container_from_inspect(inspect)
    state.upsert_workflow(
        container_id,
        workspace_volume=found.workspace_volume,
        runs_volume=found.runs_volume,
        workflow_type=found.workflow_type,
    )


def _sync_native_row(run: RunTelemetry, fired: list[alerts.Alert] | None = None) -> bool:
    """Project a run's telemetry hot-cache entry onto a dashboard row when the run is **native** — i.e."""
    if run.native is None:
        run.native = localfs.is_local_dir(run.run_dir) or localfs.is_local_dir(
            run.workspace
        )
    if not run.native:
        return False
    before = state.WORKFLOWS.get(run.run_id)
    prev = (
        (before.state, before.current_node, before.activity, before.last_session,
         tuple((g.file_path, g.question, g.kind) for g in before.gates.values()))
        if before
        else None
    )
    if not run.terminal and run.wait_kind in ("operator", "machine"):
        gate = GateInfo(
            workflow_id=run.run_id,
            file_path=run.wait_gate_path,
            question=run.wait_gate_question,
            kind=run.wait_kind,
        )
    else:
        gate = None
    gates = {gate.file_path: gate} if gate is not None else {}
    if run.terminal:
        new_state = WorkflowState.FINISHED
    elif gates:
        new_state = WorkflowState.BLOCKED
    else:
        new_state = WorkflowState.RUNNING
    wf = state.upsert_workflow(
        run.run_id,
        name=run.workflow or run.run_id[:12],
        native=True,
        workflow_type=run.workflow,
        repo_name=run.repo,
        repo_branch=run.branch,
        run_id=run.run_id,
        workspace_volume=run.workspace,
        runs_volume=run.run_dir,
        current_node=run.current_node,
        activity=run.activity,
        pid=run.pid,
        state=new_state,
    )
    wf.gates = dict(gates)
    wf.last_session = run.last_session
    _attend_gates(wf, list(wf.gates.values()))
    return prev is None or prev != (
        wf.state,
        wf.current_node,
        wf.activity,
        wf.last_session,
        tuple((g.file_path, g.question, g.kind) for g in wf.gates.values()),
    )


async def _project_native_rows(records: list) -> None:
    """After an OTLP ingest, refresh the dashboard rows of the native runs it touched and broadcast once if any changed."""
    run_ids = {r.get("run_id") for r in records if r.get("run_id")}
    changed = []
    newly_blocked = []
    fired: list[alerts.Alert] = []
    for run_id in run_ids:
        run = state.RUNS.get(run_id)
        if run is None:
            continue
        existing = state.WORKFLOWS.get(run_id)
        was_blocked = (
            existing is not None
            and existing.state == WorkflowState.BLOCKED
            and existing.last_session == run.last_session
        )
        changed.append(_sync_native_row(run, fired))
        wf = state.WORKFLOWS.get(run_id)
        if wf is not None and wf.state == WorkflowState.BLOCKED and not was_blocked:
            newly_blocked.append(wf)
    await alerting._dispatch_alerts(fired)
    for run_id in run_ids:
        run = state.RUNS.get(run_id)
        if run is not None:
            live.schedule_liveness(run)
            _ensure_gate_backfill(run)
    live.mark_fleet()
    for run_id in run_ids:
        live.mark_run(run_id)
    for wf in newly_blocked:
        if wf.gates:
            gate = next(iter(wf.gates.values()))
            await alerting._broadcast_notify(
                f"{wf.workflow_type or wf.name} is waiting on {gate.file_path}"
            )


async def _run_facts(wf: WorkflowContainer) -> tuple:
    """Seed history once per subscription; compose subsequent pushes in memory."""
    run_id = projection.run_id_of(wf)
    history = state.HISTORIES.get(run_id)
    seeded = False
    if history is None or not history.loaded:
        async with state.HISTORY_LOCK:
            history = state.HISTORIES.get(run_id)
            if history is None:
                history = LiveHistory(log_limit=projection.LOG_TRAIL_LIMIT)
            if run_id and not history.loaded:
                spans = await pools.QUERY.run(store.detail_spans, run_id)
                logs = await pools.QUERY.run(
                    store.query_logs, run=run_id, limit=projection.LOG_TRAIL_LIMIT
                )
                metric_rows = await pools.QUERY.run(
                    store.detail_metrics, run_id, projection.LOG_TRAIL_LIMIT
                )
                history.update_spans(spans)
                history.logs = logs
                history.metrics = metric_rows
                if run_dir := _native_run_dir(wf):
                    await asyncio.to_thread(live_transcript.poll, history, run_dir)
                history.loaded = True
                seeded = True
            if state.watchers_of(wf.container_id):
                state.HISTORIES[run_id] = history
    if seeded and not wf.native and sidecar_hub.get(wf.container_id) is not None:
        _schedule_tail(wf.container_id)
    facts = next(iter(alerts.live_status(run=run_id)), {}) if run_id else {}
    facts.update(history.facts())
    return state.RUNS.get(run_id), facts, history.logs, history.recent()


async def _reconcile() -> int:
    """One discovery pass: upsert every found workflow, then prune the ones whose container is gone (skipping the prune when docker is unreachable so a transient outage never wipes the fleet)."""
    found = await asyncio.to_thread(discovery.scan)
    for wf in found:
        state.WORKFLOWS[wf.container_id] = wf
    present = await asyncio.to_thread(discovery.present_container_ids)
    if present is not None:
        state.prune_workflows(present)
    return len(found)
