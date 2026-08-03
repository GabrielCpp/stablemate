---
type: concept
slug: sidecar-filesystem-watch
title: Sidecar filesystem watch
---
# Sidecar filesystem watch

Sidecar filesystem watch is the delegated filesystem-observation layer used by the [sidecar connected session](sidecar-connected-session.md). It selects which of the configured sidecar mounts can be watched, subscribes to them recursively through the portable `watchfiles` backend, and feeds the classified [sidecar websocket frame](../sidecar-websocket-frame.md) objects into the session's outbound queue until the session asks it to stop.

It replaces an earlier recursive inotify-watch installer that registered one watch descriptor per directory and maintained a caller-owned descriptor-to-path map. `watchfiles` selects the platform backend itself (inotify on Linux, FSEvents on macOS, `ReadDirectoryChangesW` on Windows) and recurses into newly created subdirectories on its own, so neither the descriptor map nor the create-a-watch-for-a-new-subtree step exists any more. The container keeps inotify; the sidecar and its tests stop being Linux-only.

- code: groom/groom/sidecar.py::_watch_roots
- code: groom/groom/sidecar.py::_watch_loop
- verify: groom/tests/test_sidecar_session.py::test_the_watch_skips_a_mount_that_is_not_mounted_yet
- verify: groom/tests/test_sidecar_session.py::test_the_watch_reports_a_gate_written_after_it_started

## Contract

- roots: the configured workspace mount and the configured runs mount, in that order, minus any that is not currently a directory.
- absent-root rule: a mount that does not exist is dropped rather than raising; `watchfiles` raises `FileNotFoundError` for a missing path, and a sidecar started before its runs volume is mounted must still open its session and serve data-plane RPCs.
- empty-root rule: with neither mount present no watch task work is performed and the loop returns immediately; the session continues without filesystem deltas.
- prune rule: directory names equal to `.git`, `node_modules`, `__pycache__`, or `.venv` — the [sidecar skip directory names](groom-sidecar-module.md#field-skip-dir-names) — are excluded from the watch. The same set is used by the pull-side gate scan, so a gate the scan reports is a gate the watch can fire on.
- change rule: additions and modifications are classified; deletions are dropped. A removed run file is not progress, and the inotify mask this replaced likewise asked for writes and creations only.
- recursion: subdirectories created after the watch starts are covered without any further registration by this layer.
- coalescing: changes arrive already batched by the backend, so a burst of writes yields one set rather than one event each; a path may therefore have been deleted again by the time it is classified.
- effects: enqueues `progress` and `blocked` frames on the caller-owned outbound queue.
- non-effects: does not send websocket frames, serialize JSON, perform residual HTTP pushes, read the checkpoint or run files itself, create directories, mutate workspace files, or decide host workflow state.
- lifecycle: one watch task per connected session, started after the `hello` frame and stopped during session cleanup by setting the shared stop event and cancelling the task.

## Algorithm

1. Collect the configured workspace and runs mounts that are directories; return when none is.
2. Subscribe recursively to those roots with the skip-directory filter and the session's stop event.
3. For each yielded batch of changes, drop deletions.
4. Classify each remaining changed path with [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event).
5. Enqueue every non-`None` frame on the session's outbound queue.
6. Exit when the stop event is set or the task is cancelled.

## Methods

### method-_watch_roots

- sig: `_watch_roots() -> list[Path]`
- abstract: false
- raises: nothing; a missing or non-directory mount is a dropped entry, not an error.
- code: groom/groom/sidecar.py::_watch_roots
- input: none; reads the module-level configured workspace and runs mount paths.
- output: the subset of those mounts that are directories, workspace first.
- effects: filesystem existence checks only.
- calls: standard-library path inspection only; it does not call another groom service symbol.

### method-_watch_loop

- sig: `_watch_loop(outbox: asyncio.Queue, stop: asyncio.Event) -> None`
- abstract: false
- raises: nothing intentionally; cancellation is the expected termination path and is handled by the caller.
- code: groom/groom/sidecar.py::_watch_loop
- input: `outbox` is the caller-owned FIFO the [sidecar outbound sender](sidecar-outbound-sender.md) drains; `stop` is the shared event the session sets during cleanup.
- output: `None`; all useful result data is the frames placed on `outbox`.
- effects: subscribes to the watchable roots, drops deletions, classifies the remaining changed paths, and enqueues the resulting frames.
- calls: [method-_watch_roots](#method-_watch_roots), [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event), and the third-party watch backend.
- algorithm:
  1. Return immediately when no configured mount is a directory.
  2. Iterate batches of changes from the recursive, filtered watch over those roots.
  3. Skip deletions within each batch.
  4. Classify each remaining path into a frame.
  5. Enqueue every frame the classifier returns.

## Related

- [Sidecar connected session](sidecar-connected-session.md) owns the watch task, the outbound queue, and the stop event.
- [method-_classify_event](../sidecar-websocket-frame.md#method-_classify_event) turns one changed path into the frame this layer enqueues.
- [Sidecar outbound sender](sidecar-outbound-sender.md) drains the queue this layer fills.
