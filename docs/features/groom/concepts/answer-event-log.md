---
type: concept
slug: answer-event-log
title: Answer event log
---
# Answer event log

Answer event log is groom's process-local, bounded history of dashboard answer attempts. The [edit detail answer textarea](../gui/screens/groom-dashboard.md#edit-detail-answer-textarea) and [send detail answer](../gui/screens/groom-dashboard.md#send-detail-answer) interactions reach it after the gate-answering layer returns an [answer result](../answer-result.md); the dashboard websocket command handler builds an [answer log entry](../answer-log-entry.md) from the submitted [dashboard websocket answer frame](../dashboard-websocket-answer-frame.md) and appends that object through [record answer log entry](#method-record-answer-log-entry).

- code: groom/groom/state.py::LOG
- code: groom/groom/state.py::record_log

## Contract

- scope: one in-memory log per groom process; it is shared by dashboard websocket command handling inside that process and is lost when the process exits.
- initialization: importing the groom state module creates the log as an empty bounded sequence before any dashboard request, websocket connection, background discovery scan, or answer command runs.
- container: bounded append-only sequence with newest entries appended at the tail and oldest entries automatically evicted after capacity is reached.
- capacity: exactly 200 retained events.
- value type: dictionary matching [answer log entry](../answer-log-entry.md) for the current answer-command producer; the storage layer itself accepts any dictionary supplied by a first-party caller.
- producer mapping: the current first-party producer is the dashboard websocket answer-command handler, which builds the entry only after receiving an [answer result](../answer-result.md) and before broadcasting the refreshed dashboard shell.
- writer: [record answer log entry](#method-record-answer-log-entry) is the only first-party mutation API for appending an answer-attempt event.
- readers: no first-party route, websocket command, UI component, serializer, or background task currently reads entries back from the log.
- retention: bounded to the newest 200 entries; appending entry 201 or later may discard the oldest retained entry.
- ordering: entries are retained in append order, which is the order in which answer-command attempts finish gate-answering inside the running process.
- append semantics: each successful call to [record answer log entry](#method-record-answer-log-entry) appends exactly one supplied dictionary at the newest end of the log; there is no batching, replacement, deduplication, sort, or merge step.
- object handling: the supplied dictionary is retained as the log member; the log layer does not clone, freeze, redact, or transform the object before storage.
- synchronization: the log has no groom-specific lock, async queue, await point, or cross-task coordination mechanism; callers that need sequencing must establish it before calling the append API.
- persistence: no disk file, database, external sink, replay protocol, acknowledgement frame, or cross-process coordination participates.
- visibility: the log is internal process state; the current dashboard surface records answer attempts into it but does not expose a route, websocket frame, or UI panel that reads it back.
- command coverage: handled answer-command successes and handled answer-command failures are both logged; frames whose command is not exactly `answer`, and exceptions raised before an [answer result](../answer-result.md) is returned, produce no answer log entry.
- failure behavior: the log has no domain-level validation or recovery path; if the underlying append operation raises, that ordinary runtime error propagates to the caller.

## Fields

### field-log-entry

- type: [answer log entry](../answer-log-entry.md)
- default: none
- required: true for appended members
- multiplicity: zero to 200 retained entries.
- ordering: newest entries appear after older retained entries.
- meaning: one completed answer attempt record containing the event discriminator, normalized container id, gate file path, success flag, and outcome message.
- producer-use: the dashboard answer-command handler passes the exact dictionary it built; the log does not clone, redact, timestamp, or add fields to the member.

## Methods

### method-record-answer-log-entry

- sig: `record_log(event: dict) -> None`
- abstract: false
- raises: no domain-specific errors; ordinary container append errors would propagate to the caller.
- code: groom/groom/state.py::record_log

Appends one already-built event dictionary to the process-local answer event log without validating, normalizing, cloning, broadcasting, or persisting it.

#### Inputs

- event: dictionary supplied by the caller; required; default none. For dashboard answer commands the dictionary matches [answer log entry](../answer-log-entry.md), but this layer itself accepts the dictionary as given and does not enforce keys or value types.

#### Return

- value: `None` after the append completes.

#### Effects

- Reads: the current process-local `LOG` deque object.
- Appends: stores the supplied event object at the newest end of `LOG` exactly once.
- Retains: at most 200 newest events; if the bounded deque is already full, the oldest retained entry is discarded by the append operation.
- Emits: no return value, acknowledgement, broadcast fragment, websocket message, or rendered UI update.
- Preserves: workflow records, gate maps, gate locks, dashboard client queues, sidecar connections, discovery scanning state, and the supplied event object's contents.
- Caller sequencing: the dashboard answer-command handler calls this method after gate-answering returns and before any success-only blocked-to-running state flip, answered-event script rendering, dashboard shell broadcast, or websocket queue write for the same attempt.
- Does not: validate the event shape, copy or freeze the dictionary, add timestamps, redact answer metadata, read or write gate files, answer containers, render HTML, broadcast dashboard updates, persist logs to disk, or expose the entry to connected clients.
- Errors: no groom-specific error is caught or translated; a runtime failure from appending to the bounded in-memory sequence propagates as-is.
- Bottoms out: the layer only calls the bounded deque append operation on `LOG`; it calls no other first-party groom symbol.

## Algorithms

### algorithm-log-initialization

- step: The groom state module is imported inside one groom process.
- step: The module creates `LOG` as an empty bounded sequence whose maximum retained length is 200 entries.
- step: The empty log is then available to first-party callers without opening files, connecting to a database, accepting websocket clients, inspecting workflow containers, or rendering dashboard HTML.

### algorithm-answer-attempt-append

- step: A caller supplies one already-built event dictionary.
- step: [record answer log entry](#method-record-answer-log-entry) appends that same dictionary object at the newest end of the process-local log.
- step: If the append makes the bounded sequence exceed 200 entries, the oldest retained entry is evicted by the bounded container.
- step: The method returns `None` and leaves client notification, dashboard rendering, workflow-state changes, and any error handling to its caller.
