"""In-memory, single-process state."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable

from groom.attention import AttentionEvent
from groom.live_history import LiveHistory
from groom.models import RunTelemetry, WorkflowContainer

WORKFLOWS: dict[str, WorkflowContainer] = {}
LOG: deque[dict] = deque(maxlen=200)
CLIENTS: set[asyncio.Queue] = set()

WATCHING: dict[asyncio.Queue, str] = {}
HISTORIES: dict[str, LiveHistory] = {}
TRANSCRIPT_TASKS: dict[str, asyncio.Task] = {}
HISTORY_LOCK = asyncio.Lock()

RUNS: dict[str, RunTelemetry] = {}

EVENT_HISTORY = 200
EVENTS: dict[str, deque[tuple[float, AttentionEvent]]] = {}
FEEDS: dict[asyncio.Queue, str] = {}

SCANNING: bool = True
FLEET_V: int = 0
REVS: dict[str, int] = {"dispatch": 0, "history": 0}
CLIENT_QUEUE_MAX = 256
WATCH_REFRESH: Callable[[str], None] | None = None

_gate_locks: dict[str, asyncio.Lock] = {}


def gate_lock(container_id: str, file_path: str) -> asyncio.Lock:
    """One lock per (container, gate file) so two browser tabs answering the same gate race on the lock instead of both writing."""
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
    """Drop every tracked workflow whose container no longer exists, returning the removed ids."""
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
    """Drop telemetry hot-cache entries (and any native dashboard row they back) for the given run ids — the eviction that bounds ``RUNS``/``WORKFLOWS`` growth on a long-lived groom."""
    from groom import live

    for run_id in run_ids:
        live.cancel_liveness(run_id)
        RUNS.pop(run_id, None)
        EVENTS.pop(run_id, None)
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
    WATCHING.pop(queue, None)
    _release_histories()


def add_feed(queue: asyncio.Queue, run_id: str) -> None:
    FEEDS[queue] = run_id


def remove_feed(queue: asyncio.Queue) -> None:
    FEEDS.pop(queue, None)


def record_event(run_id: str, event: AttentionEvent, ts: float) -> None:
    EVENTS.setdefault(run_id, deque(maxlen=EVENT_HISTORY)).append((ts, event))


def feeds_of(run_id: str) -> list[asyncio.Queue]:
    return [queue for queue, fed in FEEDS.items() if fed == run_id]


def watch(queue: asyncio.Queue, run_id: str) -> None:
    """Record which run one tab has open (empty id = watching nothing)."""
    if run_id:
        WATCHING[queue] = run_id
    else:
        WATCHING.pop(queue, None)
    _release_histories()


def _release_histories() -> None:
    from groom import live

    watched = {
        wf.run_id or wf.container_id
        for cid in WATCHING.values()
        if (wf := WORKFLOWS.get(cid)) is not None
    }
    for run_id in list(HISTORIES):
        if run_id not in watched:
            del HISTORIES[run_id]
    for run_id in list(TRANSCRIPT_TASKS):
        if run_id not in watched:
            TRANSCRIPT_TASKS.pop(run_id).cancel()
    live.release_unwatched()


def watchers_of(run_id: str) -> list[asyncio.Queue]:
    return [queue for queue, watched in WATCHING.items() if watched == run_id]


def watched_ids() -> set[str]:
    """Every run some tab currently has open."""
    return set(WATCHING.values())


def new_client_queue() -> asyncio.Queue:
    return asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)


def _overflowed(queue: asyncio.Queue) -> None:
    """A tab that stopped reading loses its backlog and gets one fresh snapshot, and its open run is sent again."""
    from groom import live

    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    queue.put_nowait(live.snapshot())
    run_id = WATCHING.get(queue)
    if run_id and WATCH_REFRESH is not None:
        WATCH_REFRESH(run_id)


def offer(queue: asyncio.Queue, message: dict) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        _overflowed(queue)


def broadcast_nowait(message: dict) -> None:
    for queue in list(CLIENTS):
        offer(queue, message)


async def send(queue: asyncio.Queue, message: dict) -> None:
    offer(queue, message)


async def broadcast(message: dict) -> None:
    """Fan one JSON message out to every open dashboard tab."""
    broadcast_nowait(message)
