---
type: concept
slug: per-gate-answer-lock
title: Per-gate answer lock
---
# Per-gate answer lock

Per-gate answer lock is groom's process-local serialization primitive for one operator answer target: the pair of a [workflow container](workflow-container.md) id and a gate file path inside that workflow's workspace volume. The [gate-answering layer](gate-answering-layer.md) obtains this lock before it re-reads the gate file, rejects stale submissions, writes the answered file, clears the in-memory [gate info](gate-info.md), and decides whether a stopped container needs the [stopped container start fallback](stopped-container-start-fallback.md), while the [workflow registry](workflow-registry.md) prunes locks for containers that discovery confirms have vanished.

- code: groom/groom/state.py::_gate_locks
- code: groom/groom/state.py::gate_lock
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed

## Contract

- scope: one in-memory lock registry per groom process; locks coordinate only concurrent asynchronous answer handlers inside that process and do not coordinate with another groom process, Docker, the container's own wait script, or direct file edits outside groom.
- identity: a lock is scoped to exactly one `(container_id, file_path)` pair, so two submissions for the same gate serialize and submissions for different gates can proceed independently.
- creation: the first request for a pair creates an unlocked `asyncio.Lock` and records it under the computed lock key before returning; later requests for the same pair return the same lock object until it is forgotten or the process exits.
- creation atomicity: lookup and first-lock insertion contain no await point, so within groom's single running event loop two same-pair callers cannot interleave between the missing-lock check and storing the new lock.
- acquisition owner: the caller owns `async with lock`; the lock factory only returns the lock and does not acquire, release, time out, inspect, or mutate any gate file.
- scheduling contract: the registry exposes no priority, queue length, fairness, owner identity, wait timeout, or cancellation policy of its own; accepted answer ordering is determined by whichever same-gate caller enters the locked answer region first and by the gate file status re-read inside that region.
- lookup precondition: the dashboard answer path rejects an empty workspace-volume value before requesting a lock, so a submission that cannot identify the workspace volume does not create a lock entry.
- answer-safety role: while the lock is held, the answer path performs the authoritative file read, status check, answer text construction, file write, post-write gate cleanup, running-state check, and stopped-container restart fallback, so a second browser tab waits for the first attempt's terminal result before it can re-read the gate file.
- failure behavior: missing gate files, already-answered gate files, and failed answer writes return failure while releasing the acquired lock; those failures keep the lock registry entry for future same-pair attempts and do not clear the workflow's in-memory gate record.
- lifetime: locks remain in the registry after successful answers and after individual gates are cleared; they are not evicted by lookup, acquisition, release, answer success, stale-answer rejection, or write failure. They are forgotten when `prune_workflows` removes the containing workflow container or when the groom process exits.
- cleanup: pruning a removed workflow deletes every lock whose internal key starts with that container id and the lock-key separator, preventing the process-local lock map from growing without bound across deleted containers.
- validation boundary: the lock key uses the caller-supplied strings as-is; container id normalization and safe relative-path validation happen in callers and Docker file helpers, not in the lock registry, so distinct spellings produce distinct lock identities.
- cleanup namespace: removed-container cleanup uses a string-prefix match of `container_id + "::"`; this is behavior-equivalent for groom's normalized Docker container ids, and the lock registry does not escape or defend arbitrary ids that themselves contain the separator.
- non-effect: does not validate answer text, detect stale gate state, write `STATUS: ANSWERED`, clear the workflow's gate map, change workflow state, restart containers, broadcast websocket HTML, append logs, or persist any state outside process memory.

## Fields

### field-container-id

- type: `str`
- default: none
- required: true
- meaning: workflow container identifier used as the first part of the lock identity and as the cleanup prefix when a workflow container is pruned.
- constraints: treated as an opaque non-normalized string by the lock factory; callers are responsible for supplying the same value used by the [workflow container](workflow-container.md) registry entry.

### field-file-path

- type: `str`
- default: none
- required: true
- meaning: gate context file path used as the second part of the lock identity, matching the key in a workflow container's open gate map and the file path passed to the gate-answering layer.
- constraints: not sanitized by the lock factory; unsafe or traversal-like paths are rejected later by workspace volume file helpers when an answer attempts to read or write the file.

### field-lock-key

- type: `str`
- default: computed as `f"{container_id}::{file_path}"`
- required: true
- meaning: internal process-local dictionary key that combines the container id and gate file path into one lookup value.
- constraints: the `::` separator is an internal namespace boundary only; callers never receive or submit this key directly, and the key is not parsed except when workflow pruning matches a removed container id prefix. Correct cleanup assumes the container-id namespace supplied by callers does not contain the separator.

### field-lock-instance

- type: `asyncio.Lock`
- default: created unlocked on first lookup for a lock key
- required: true
- meaning: asynchronous mutual-exclusion object returned to the answer path so same-gate answer attempts run one at a time.
- constraints: protects only code that awaits the returned lock; it has no file-system, Docker, database, or cross-process visibility.

### field-lock-registry

- type: `dict[str, asyncio.Lock]`
- default: `{}` at groom process start
- required: true
- meaning: process-local map from lock key to lock instance, shared by all answer handlers in the running groom server process.
- constraints: loses all contents on process exit; entries are removed only by workflow pruning for vanished containers, not by successful individual answers.

## Methods

### method-gate-lock

- sig: `gate_lock(container_id: str, file_path: str) -> asyncio.Lock`
- abstract: false
- raises: no domain-specific errors; ordinary memory allocation errors while creating a new lock would propagate.
- code: groom/groom/state.py::gate_lock
- verify: groom/tests/test_state.py::test_prune_also_forgets_gate_locks_of_removed

Returns the shared lock for one container-and-gate-file pair, creating it when the pair has not been seen before in the current process.

#### Effects

- Computes: the internal lock key from the supplied `container_id`, the literal `::` separator, and the supplied `file_path`.
- Reads: the process-local lock registry for an existing lock under that key.
- Creates: a new unlocked `asyncio.Lock` only when the key is absent.
- Writes: stores the new lock in the registry before returning it when the key was absent, so later lookups for the same pair share the same object.
- Emits: the existing or newly-created lock object for the caller to acquire.
- Preserves: the existing lock object and registry entry when the key is already present; repeated lookups for the same pair do not replace, wrap, reset, acquire, or release the lock.
- Serializes: contains no await point during lookup or creation, so the returned object is installed before any caller can suspend on it.
- Preserves: workflow registry records, gate maps, dashboard clients, logs, Docker state, gate file text, and lock entries for other container/file pairs.
- Does not: acquire the lock, release the lock, validate the file path, inspect gate status, read or write Docker volumes, clear gates, restart containers, broadcast HTML, or prune old locks.

## Algorithms

### algorithm-answer-serialization

- step: A dashboard answer request reaches the [gate-answering layer](gate-answering-layer.md) with a container id, gate file path, answer text, and workspace volume.
- step: If the request has no workspace volume, the answer path returns an [answer result](../answer-result.md) failure before asking for a lock, reading files, mutating workflow state, or changing the lock registry.
- step: The gate-answering layer asks for the per-gate answer lock for that container id and gate file path.
- step: The answer path enters the returned lock before reading the current gate file from the workspace volume.
- step: While still holding the lock, it rejects the submission if the gate file cannot be read or unless the freshly-read file status is `AWAITING_OPERATOR`.
- step: While still holding the lock, it writes the answered gate file and clears the in-memory open gate only after the write succeeds.
- step: While still holding the lock after a successful write, it checks whether the workflow container is running and performs the stopped-container restart fallback only when the container is stopped.
- step: A second same-gate submission waits until the first attempt exits the locked region, then performs its own fresh read and returns the stale-answer rejection instead of clobbering the first write.

### algorithm-lock-cleanup

- step: A discovery reconciliation pass determines the set of Docker container ids still present.
- step: The [prune workflows](workflow-registry.md#method-prune-workflows) method removes registry entries for ids absent from that set.
- step: For each removed id, pruning deletes every lock registry entry whose key starts with that id plus the `::` separator.
- step: Locks for containers still present are preserved, including locks for gates that may already have been answered.
