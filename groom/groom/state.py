"""In-memory, single-process state. Plain module-level objects — no Redis, no
broker, no ``app.state`` — per groom's single-process constraint.
"""

from __future__ import annotations

import asyncio
from collections import deque

from groom.models import RunTelemetry, WorkflowContainer

WORKFLOWS: dict[str, WorkflowContainer] = {}
LOG: deque[dict] = deque(maxlen=200)
CLIENTS: set[asyncio.Queue] = set()

# queue → the id of the run whose detail pane that tab currently has open.
#
# The fleet is a fleet-wide fact and goes to every tab; a detail slice is a
# consequence of one tab's selection and goes only to the tabs that asked for it.
# Without this map the choice is between broadcasting every open run's detail to
# everyone (bandwidth proportional to tabs × runs, and each tab discarding almost
# all of it) or having each tab poll for its own — which is what this replaces.
WATCHING: dict[asyncio.Queue, str] = {}

# Telemetry hot cache: run_id → alert-rule state, updated on every OTLP ingest
# (groom.alerts). The durable copy is groom.store's SQLite file; this map only
# carries what the rules need between ingests. Single event loop ⇒ no locks.
RUNS: dict[str, RunTelemetry] = {}

# True while the initial (or a manual) container-discovery pass is still in
# flight. The UI renders a spinner instead of the "no workers" empty state so a
# not-yet-scanned fleet doesn't look finished-and-empty. Single process / single
# event loop, so a plain bool needs no lock. Starts True: groom serves the page
# immediately and discovers in the background (see app._background_scan).
SCANNING: bool = True

_gate_locks: dict[str, asyncio.Lock] = {}


def gate_lock(container_id: str, file_path: str) -> asyncio.Lock:
    """One lock per (container, gate file) so two browser tabs answering the
    same gate race on the lock instead of both writing.
    """
    key = f"{container_id}::{file_path}"
    lock = _gate_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _gate_locks[key] = lock
    return lock


def upsert_workflow(container_id: str, **fields: object) -> WorkflowContainer:
    wf = WORKFLOWS.get(container_id)
    if wf is None:
        name = str(fields.pop("name", "") or "") or container_id[:12]
        wf = WorkflowContainer(container_id=container_id, name=name)
        WORKFLOWS[container_id] = wf
    for key, value in fields.items():
        if value is not None and hasattr(wf, key):
            setattr(wf, key, value)
    return wf


def clear_gate(container_id: str, file_path: str) -> None:
    wf = WORKFLOWS.get(container_id)
    if wf is None:
        return
    wf.gates.pop(file_path, None)


def prune_workflows(present_ids: set[str]) -> list[str]:
    """Drop every tracked workflow whose container no longer exists, returning
    the removed ids. Also forgets their per-gate locks so the maps don't grow
    unbounded across a long-lived groom process.
    """
    # Native rows have no container, so the docker present-set says nothing about
    # them — their state follows their own telemetry (running while it beats, not
    # running once it stops), and they leave for good via ``evict_runs``.
    removed = [
        cid
        for cid, wf in WORKFLOWS.items()
        if not wf.native and cid not in present_ids
    ]
    for cid in removed:
        WORKFLOWS.pop(cid, None)
        for key in [k for k in _gate_locks if k.startswith(f"{cid}::")]:
            _gate_locks.pop(key, None)
    return removed


def evict_runs(run_ids: list[str]) -> None:
    """Drop telemetry hot-cache entries (and any native dashboard row they back)
    for the given run ids — the eviction that bounds ``RUNS``/``WORKFLOWS`` growth
    on a long-lived groom. Docker rows are left to the discovery prune; only native
    rows (keyed by run_id, with no container behind them) are removed here, along
    with their per-gate locks so those maps don't leak either.
    """
    for run_id in run_ids:
        RUNS.pop(run_id, None)
        wf = WORKFLOWS.get(run_id)
        if wf is not None and wf.native:
            WORKFLOWS.pop(run_id, None)
            for key in [k for k in _gate_locks if k.startswith(f"{run_id}::")]:
                _gate_locks.pop(key, None)


def record_log(event: dict) -> None:
    LOG.append(event)


def add_client(queue: asyncio.Queue) -> None:
    CLIENTS.add(queue)


def remove_client(queue: asyncio.Queue) -> None:
    CLIENTS.discard(queue)
    # A closed tab watches nothing. Forgotten here rather than by the caller so a
    # disconnect can never leave a subscription pointing at a queue nobody reads,
    # which would grow WATCHING for the life of the process.
    WATCHING.pop(queue, None)


def watch(queue: asyncio.Queue, run_id: str) -> None:
    """Record which run one tab has open (empty id = watching nothing)."""
    if run_id:
        WATCHING[queue] = run_id
    else:
        WATCHING.pop(queue, None)


def watchers_of(run_id: str) -> list[asyncio.Queue]:
    return [queue for queue, watched in WATCHING.items() if watched == run_id]


def watched_ids() -> set[str]:
    """Every run some tab currently has open — what the live clock has to refresh."""
    return set(WATCHING.values())


async def send(queue: asyncio.Queue, message: dict) -> None:
    await queue.put(message)


async def broadcast(message: dict) -> None:
    """Fan one JSON message out to every open dashboard tab.

    Messages are dicts, not strings: the socket and ``GET /api/state`` deliver
    the same shapes (see :mod:`groom.projection`) and the browser owns rendering,
    so nothing here knows what a tab will do with a ``state`` frame.
    """
    for queue in list(CLIENTS):
        await queue.put(message)
