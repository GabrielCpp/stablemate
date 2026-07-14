"""In-memory, single-process state. Plain module-level objects — no Redis, no
broker, no ``app.state`` — per groom's single-process constraint.
"""

from __future__ import annotations

import asyncio
from collections import deque

from .models import RunTelemetry, WorkflowContainer

WORKFLOWS: dict[str, WorkflowContainer] = {}
LOG: deque[dict] = deque(maxlen=200)
CLIENTS: set[asyncio.Queue] = set()

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
        name = fields.pop("name", None) or container_id[:12]
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
    removed = [cid for cid in WORKFLOWS if cid not in present_ids]
    for cid in removed:
        WORKFLOWS.pop(cid, None)
        for key in [k for k in _gate_locks if k.startswith(f"{cid}::")]:
            _gate_locks.pop(key, None)
    return removed


def record_log(event: dict) -> None:
    LOG.append(event)


def add_client(queue: asyncio.Queue) -> None:
    CLIENTS.add(queue)


def remove_client(queue: asyncio.Queue) -> None:
    CLIENTS.discard(queue)


async def broadcast(html_fragment: str) -> None:
    for queue in list(CLIENTS):
        await queue.put(html_fragment)
