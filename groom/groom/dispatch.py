"""groom's dispatch queues: named, config-declared lanes that launch a workflow console script per enqueued item, capped at each queue's own concurrency."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from typing import Any

from workhorse._vendor.stablemate_core import config as core_config
from workhorse.config_run import AgentResilience
from workhorse.runner.process import ProcessSupervisor

from groom import store

logger = logging.getLogger(__name__)


class UnknownQueue(Exception):
    """Enqueued against a name with no ``[groom.dispatch.<name>]`` entry."""


_SLOTS: dict[str, threading.Semaphore] = {}
_SLOTS_LOCK = threading.Lock()


def reset() -> None:
    """Forget every queue's slot — for tests, and a fresh process."""
    with _SLOTS_LOCK:
        _SLOTS.clear()


def _slot(queue: str, concurrency: int) -> threading.Semaphore:
    """The semaphore for this queue, creating it at its configured size on first use."""
    with _SLOTS_LOCK:
        existing = _SLOTS.get(queue)
        if existing is None:
            occupied = len(store.dispatch_running_for_queue(queue))
            existing = threading.Semaphore(max(0, concurrency - occupied))
            _SLOTS[queue] = existing
        return existing


def queues() -> dict[str, core_config.DispatchQueueSettings]:
    """Every configured queue, keyed by name."""
    try:
        return core_config.resolve_dispatch_queues()
    except Exception:
        logger.warning("dispatch: could not read the dispatch queue config")
        return {}


def _launch(item_id: str, command: str, params: dict[str, Any]) -> subprocess.Popen[str]:
    """Spawn ``<command> run --params <json> --run-id <item_id>``, as its own process group, exactly the way `attend._launch` spawns `claude -p`."""
    launch_params = dict(params)
    cli = str(launch_params.pop("cli", "") or "").strip()
    argv = [command, "run", "--params", json.dumps(launch_params), "--run-id", item_id]
    if cli:
        argv.extend(["--cli", cli])
    supervisor = ProcessSupervisor()
    return supervisor.spawn(
        argv,
        f"dispatch:{item_id}",
        resilience=AgentResilience(),
        cwd=os.getcwd(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )


def _own(item_id: str, queue: str, proc: subprocess.Popen[str], slot: threading.Semaphore) -> None:
    """Wait on the item's process, flip its row, and free the queue's slot."""

    def _wait() -> None:
        code: int | None = None
        try:
            code = proc.wait()
        except Exception:
            logger.exception("dispatch: lost the process for %s/%s", queue, item_id)
        status = store.DISPATCH_DONE if code == 0 else store.DISPATCH_FAILED
        if not store.dispatch_finish(item_id, status=status, exit_code=code):
            return
        slot.release()
        _drain(queue)

    threading.Thread(target=_wait, name=f"dispatch-own-{item_id}", daemon=True).start()


def enqueue(queue: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record a new item as `pending` and try to launch it immediately."""
    settings = queues().get(queue)
    if settings is None:
        raise UnknownQueue(queue)
    item_id = uuid.uuid4().hex[:12]
    expanded = _apply_templates(settings, params or {})
    store.dispatch_enqueue(item_id, queue=queue, command=settings.command, params=expanded)
    _drain(queue)
    return store.dispatch_get(item_id) or {}


def _apply_templates(
    settings: core_config.DispatchQueueSettings, params: dict[str, Any]
) -> dict[str, Any]:
    """Expand each param whose queue-config field declares a ``template``."""
    result = dict(params)
    for param in settings.params:
        if not param.template:
            continue
        value = result.get(param.name)
        if value is None:
            continue
        result[param.name] = param.template.replace("{value}", str(value))
    return result


def _drain(queue: str) -> None:
    """Launch as many `pending` items on this queue as its free slots allow."""
    settings = queues().get(queue)
    if settings is None:
        return
    slot = _slot(queue, settings.concurrency)
    for row in store.dispatch_pending_for_queue(queue):
        if not slot.acquire(blocking=False):
            return
        item_id = str(row.get("item_id") or "")
        try:
            proc = _launch(item_id, settings.command, row.get("params") or {})
        except Exception:
            logger.exception("dispatch: could not launch %s/%s", queue, item_id)
            slot.release()
            store.dispatch_finish(item_id, status=store.DISPATCH_FAILED, exit_code=None)
            continue
        store.dispatch_start(item_id, run_id=item_id, pid=proc.pid)
        _own(item_id, queue, proc, slot)


def cancel_pending(item_id: str) -> bool:
    """Drop a still-`pending` item before it ever spawns anything."""
    return store.dispatch_cancel_pending(item_id)


def stop(item_id: str) -> bool:
    """Kill a running item's process group and flip its row to `cancelled`."""
    row = store.dispatch_get(item_id)
    if row is None or row.get("status") != store.DISPATCH_RUNNING:
        return False
    pid = row.get("pid")
    if isinstance(pid, int) and pid > 0:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except OSError:
                break
            time.sleep(0.2)
    won = store.dispatch_finish(item_id, status=store.DISPATCH_CANCELLED, exit_code=None)
    if not won:
        return False
    queue = str(row.get("queue") or "")
    settings = queues().get(queue)
    if settings is not None:
        _slot(queue, settings.concurrency).release()
        _drain(queue)
    return True


def _alive(pid: Any) -> bool:
    """Whether that pid is still a process — identical to `attend._alive`."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def recover_orphans() -> int:
    """Reconcile every row still saying `running` after a groom restart."""
    closed = 0
    for row in store.dispatch_orphans():
        item_id = str(row.get("item_id") or "")
        if not item_id or _alive(row.get("pid")):
            continue
        store.dispatch_finish(item_id, status=store.DISPATCH_FAILED, exit_code=None)
        closed += 1
    return closed


def queue_status() -> list[dict[str, Any]]:
    """Every configured queue with its concurrency and current occupancy — the whole answer to `GET /api/dispatch/queues` in one place, off the route module."""
    result = []
    for name, settings in sorted(queues().items()):
        running = store.dispatch_running_for_queue(name)
        result.append(
            {
                "name": name,
                "command": settings.command,
                "concurrency": settings.concurrency,
                "running": len(running),
                "params": [param.as_dict() for param in settings.params],
            }
        )
    return result
