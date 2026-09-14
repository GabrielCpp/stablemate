"""groom's dispatch queues: named, config-declared lanes that launch a workflow
console script per enqueued item, capped at each queue's own concurrency.

See ``docs/plans/groom-dispatch-queue-and-loop-runner.md`` §3 for the full design.
This module is deliberately the smaller sibling of :mod:`groom.attend`, not a
rewrite of it: the shape (mint an id, write the row before the first byte, own the
process from a daemon thread, flip the row at exit) is copied whole, and the one
real difference is the dedupe rule. ``attend`` allows exactly one attendant per run,
forever, tracked by run id; a dispatch queue allows up to ``concurrency`` items
running *at once*, tracked by a counting semaphore per queue name.

**Queues are static.** They come only from ``[groom.dispatch.<name>]`` in the
unified home config (:func:`core_config.resolve_dispatch_queues`) — there is no
call anywhere in groom that creates one. Enqueuing against a name with no queue
config is a no-op that raises :class:`UnknownQueue`, not a queue minted on the fly.

**Boot recovery does not resume dispatch's own work.** A ``running`` row found dead
at startup is marked ``failed`` and left there (§3.5) — unlike ``attend.recover_orphans``,
which relaunches into the same row. A dispatch item can have side effects an operator
does not want silently replayed, so the honest reading of "groom died mid-item" is
"that attempt failed," and re-running it is a decision for whoever enqueues, not for
groom's own boot path.
"""

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


#: One counting semaphore per queue name, sized to that queue's configured
#: concurrency and built lazily on first use. A module global rather than something
#: threaded through every call: the semaphores' whole job is to be shared state that
#: outlives any one request, the same reason `_LEDGER` is a module global in `attend`.
_SLOTS: dict[str, threading.Semaphore] = {}
_SLOTS_LOCK = threading.Lock()


def reset() -> None:
    """Forget every queue's slot — for tests, and a fresh process.

    A slot's size is fixed at first use (see :func:`_slot`), so a test that enqueues
    the same queue name at two different concurrencies needs this between them, the
    same reason `attend.reset` exists for `_LEDGER`.
    """
    with _SLOTS_LOCK:
        _SLOTS.clear()


def _slot(queue: str, concurrency: int) -> threading.Semaphore:
    """The semaphore for this queue, creating it at its configured size on first use.

    Not resized on a later config change: a queue whose cap is edited while items are
    in flight keeps the semaphore it started with until groom restarts, which is the
    same "no signal, no restart needed for most things, but this one thing needs a
    reload" tradeoff `attend.settings()` avoids by never sizing anything at all.

    Sized down at creation by however many of this queue's rows are already `running`
    — an alive orphan `recover_orphans` left alone (§3.5) still occupies a real slot in
    the process it is actually running in, and this is a fresh process with no memory
    of ever launching it. Without this, a groom restart with one alive orphan on a
    `concurrency=2` queue would hand out 2 *more* permits on top of the one the orphan
    already holds — a hard cap the config promises and the semaphore alone cannot keep
    once the process that counted it is gone.
    """
    with _SLOTS_LOCK:
        existing = _SLOTS.get(queue)
        if existing is None:
            occupied = len(store.dispatch_running_for_queue(queue))
            existing = threading.Semaphore(max(0, concurrency - occupied))
            _SLOTS[queue] = existing
        return existing


def queues() -> dict[str, core_config.DispatchQueueSettings]:
    """Every configured queue, keyed by name. Re-read per call, like `attend.settings`."""
    try:
        return core_config.resolve_dispatch_queues()
    except Exception:
        logger.warning("dispatch: could not read the dispatch queue config")
        return {}


def _launch(item_id: str, command: str, params: dict[str, Any]) -> subprocess.Popen[str]:
    """Spawn ``<command> run --params <json> --run-id <item_id>``, as its own process
    group, exactly the way `attend._launch` spawns `claude -p`.

    ``--run-id`` is the item id itself: a workflow console script names its own run
    directory from it, so a dispatch item's run artifacts are addressable by the id
    the queue already gave it, with nothing to look up in between.
    """
    supervisor = ProcessSupervisor()
    return supervisor.spawn(
        [command, "run", "--params", json.dumps(params), "--run-id", item_id],
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
    """Wait on the item's process, flip its row, and free the queue's slot. No deadline
    — an item that runs for a day is not a failure, the same rule `attend._own` uses.
    """

    def _wait() -> None:
        code: int | None = None
        try:
            code = proc.wait()
        except Exception:
            logger.exception("dispatch: lost the process for %s/%s", queue, item_id)
        finally:
            slot.release()
        status = store.DISPATCH_DONE if code == 0 else store.DISPATCH_FAILED
        store.dispatch_finish(item_id, status=status, exit_code=code)
        # The slot just freed is this queue's own signal to launch its next `pending`
        # item — without this call a queue that never gets `stop`ped would drain only
        # once, at capacity, and then sit on a full backlog forever.
        _drain(queue)

    threading.Thread(target=_wait, name=f"dispatch-own-{item_id}", daemon=True).start()


def enqueue(queue: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record a new item as `pending` and try to launch it immediately.

    Recording and launching are two steps, not one: the row exists (and is visible to
    `GET /api/dispatch/{queue}/items`) whether or not a slot is free right now, and a
    queue at capacity simply leaves the new row `pending` for the next release to pick
    up (see :func:`_drain`).
    """
    settings = queues().get(queue)
    if settings is None:
        raise UnknownQueue(queue)
    item_id = uuid.uuid4().hex[:12]
    store.dispatch_enqueue(item_id, queue=queue, command=settings.command, params=params or {})
    _drain(queue)
    return store.dispatch_get(item_id) or {}


def _drain(queue: str) -> None:
    """Launch as many `pending` items on this queue as its free slots allow.

    Called after every enqueue and after every item finishes — there is no poller and
    no timer, the same "an announcement triggers the check" shape `attend` uses for
    its own dispatch: a slot freeing up *is* the announcement.
    """
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
    """Kill a running item's process group and flip its row to `cancelled`.

    `SIGTERM` then `SIGKILL`, the same escalation `attend.stop` uses — a plain
    `dispatch_items.command` is an arbitrary workflow console script, not
    necessarily one that understands the `workhorse-<name> control stop` protocol,
    so a signal to the whole process group is the one mechanism guaranteed to work
    against any of them.
    """
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
    store.dispatch_finish(item_id, status=store.DISPATCH_CANCELLED, exit_code=None)
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
    """Reconcile every row still saying `running` after a groom restart. Returns how
    many were marked `failed`.

    Alive → left alone: a dispatch item's own process outlives groom's restart (it
    was started detached, in its own session), so the running row is still true and
    groom simply resumes watching nothing in particular — the next `_drain` call for
    that queue will see it occupying a slot once the config is read again. Dead → the
    row is closed as `failed`, never relaunched (§3.5, and the module docstring above).
    """
    closed = 0
    for row in store.dispatch_orphans():
        item_id = str(row.get("item_id") or "")
        if not item_id or _alive(row.get("pid")):
            continue
        store.dispatch_finish(item_id, status=store.DISPATCH_FAILED, exit_code=None)
        closed += 1
    return closed


def queue_status() -> list[dict[str, Any]]:
    """Every configured queue with its concurrency and current occupancy — the whole
    answer to `GET /api/dispatch/queues` in one place, off the route module."""
    result = []
    for name, settings in sorted(queues().items()):
        running = store.dispatch_running_for_queue(name)
        result.append(
            {
                "name": name,
                "command": settings.command,
                "concurrency": settings.concurrency,
                "running": len(running),
            }
        )
    return result
