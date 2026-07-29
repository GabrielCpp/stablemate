---
type: concept
slug: runs-fleet-view
title: Runs fleet view
status: implemented
id: stablemate-2
area: groom
---
# Runs fleet view

The runs fleet view is the `runs` array inside the [dashboard state payload](dashboard-state-payload.md): one row per [workflow container](concepts/workflow-container.md) groom knows about, already ordered by how much it deserves the operator's attention, already carrying every label the row displays. It is projected by the [groom projection module](concepts/groom-projection-module.md) and rendered by the [run row](gui/screens/groom-dashboard.md#run-row) component.

It is the whole fleet, not a needs-you-now subset. An earlier design showed only workflows holding an open [gate info](concepts/gate-info.md) record and kept everything else in a separate tree; that split meant a run that had silently died was in neither place an operator was looking. Ordering carries that concern instead: blocked runs sort first because they are waiting on *you*, then alive runs, then runs that stopped reporting, then finished ones.

Every row is data. The state dot, the type badge's hue, the liveness chip, the one-line "doing" summary, and the optional [run question preview](concepts/run-question-preview.md) are all fields the server computed; the client assigns them as text and class names and never as markup.

- code: groom/groom/projection.py::fleet_rows
- refs: [dashboard state payload](dashboard-state-payload.md), [groom projection module](concepts/groom-projection-module.md), [run question preview](concepts/run-question-preview.md), [workflow state](concepts/workflow-state.md), [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md), [dashboard client store](concepts/dashboard-client-store.md)
- verify: groom/tests/test_projection.py::test_fleet_rows_include_every_instance
- verify: groom/tests/test_projection.py::test_fleet_rows_order_blocked_then_live_then_dead_then_finished
- verify: groom/tests/test_projection.py::test_liveness_is_unknown_without_telemetry
- verify: groom/tests/test_projection.py::test_finished_row_carries_its_exit_hint
- verify: groom/tests/test_projection.py::test_query_filters_the_fleet
- verify: groom/tests/test_projection.py::test_run_message_row_matches_the_same_row_in_the_state_message
- verify: groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup

## Contract

- purpose: give a tab everything it needs to draw the fleet list in one JSON array, with no second request per row and no judgement left to the client.
- source: the caller supplies a snapshot list of workflow containers, commonly the whole in-memory [workflow registry](concepts/workflow-registry.md). Telemetry is looked up per row from the run telemetry hot cache.
- eligibility: every supplied workflow produces a row. Gate presence, state, liveness, and exit code affect a row's *content and order*, never its inclusion.
- order: by `(rank, name)` — blocked first, then alive, then presumed-dead, then finished, ties broken by workflow name ascending. Sorting server-side is what keeps a 5-second push from reshuffling the list under the operator's cursor.
- rank derivation: `blocked` is rank 0 regardless of liveness; a `finished` workflow or one whose telemetry reports terminal is rank 3; otherwise rank 1 when liveness is `live` and rank 2 when it is not.
- liveness is a telemetry question, and the only one asked is *is this run emitting right now*: a run is `live` when its most recent heartbeat, span, or first-seen stamp is within the server-side liveness window, `dead` when it is observably silent past it, `done` when its own telemetry reported a terminal for the session now running, and `unknown` when it never exported telemetry at all. `dead` must mean *observed silent*, never *unobserved*.
- telemetry outranks the container: a workflow whose container reports finished is still `live` while its run keeps beating. Only a run with no telemetry at all falls back to the container's state.
- a terminal verdict is scoped to one session and never latches: `run_id` is derived from the run dir, so `--resume-run` reuses it, and any signal stamped after the recorded terminal clears the verdict. History — an earlier session's root span, an exited container — cannot make a run that is emitting read as stopped.
- label plus number: every judgement label ships beside its raw input — `live_label` beside `silence_s`, `mini` beside `node_elapsed_s` and `turn_idle_s`, `exit_hint` beside `exit_code` — so the client can re-format without re-deciding.
- row gate: a row's gate fields come from the first open gate after sorting the workflow's gates by file path. `gate_count` reports how many are open, so the pane can say there are more.
- doing line: the single line under the row title is the gate file path when the run is parked on a gate, else its exit hint, else the activity it stamped, else its raw node id — in that order, because the gate is the thing the operator has to go answer.
- question condition: `question` is non-empty only when the run is blocked *and* has a gate. A gated `running`, `idle`, or `finished` run shows the gate path without a preview.
- server-side query: `fleet_rows` accepts a query and drops non-matching rows. It is used by [get dashboard state](http/groom.md#get-dashboard-state)'s `q` parameter; the websocket push never passes one, because a filtered push would give every tab one tab's filter.
- query matching: case-insensitive substring over workflow name, repository name, repository branch, workflow type, current node, run id, activity, and every open gate file path. It is not trimmed, tokenized, globbed, or regex-matched.
- query exclusions: container id, gate question text, gate status, answer text, and exit-code hints are not server-side haystacks.
- client-side query: the fleet component filters again in the browser over the row's own fields, because the fleet is small and the server pushes the whole thing on every tick — a server-filtered live list would be clobbered by the next push. The two filters are independent by design and neither is the other's fallback.
- fleet counts: filtering never changes the status counts. Those are fleet-wide, computed from the unfiltered snapshot, because a status bar narrowed by one tab's search box misreports the fleet it claims to describe.
- empty versus loading: an empty result is rendered as the discovery spinner only when the [dashboard discovery scanning flag](concepts/dashboard-discovery-scanning-flag.md) is true *and* no query is active; a query that matches nothing renders the ordinary empty state even mid-scan, because there an empty result is the honest answer.
- delta identity: a single-run push carries a row of exactly this shape, so the client merges it into the array by id and re-sorts by the same `(rank, name)` key rather than maintaining a second merge rule.
- selection handoff: each row carries its container id; selection, detail fetching, and the `watch` subscription are the client's, not this projection's.
- JSON only: every field is a JSON primitive. No dataclass, enum, or `datetime` escapes; `state` is the enum's string value and `native` is a real boolean.
- no markup, no escaping: rows carry text, not HTML. Gate questions travel raw and are rendered as text, so there is no escape step whose omission could become an injection.
- state mutation: projecting the fleet mutates nothing — not workflow containers, gates, telemetry, registry membership, the scanning flag, or websocket clients.

## Fields

### field-workflows

- type: `list[WorkflowContainer]`
- default: none
- required: true
- meaning: the workflow snapshot to project. Every entry yields a row unless a query excludes it.

### field-query

- type: `str`
- default: `""`
- required: false
- meaning: the server-side filter, supplied only by the state endpoint's `q` parameter.

### field-now

- type: `float | None`
- default: `None`, meaning wall-clock time
- required: false
- meaning: the injectable clock every liveness and duration field is computed against.

### field-rows

- type: `list[dict]`
- default: `[]`
- required: true
- meaning: the projected rows in display order. An empty list is a successful result, not an error.

### field-row-identity

- type: `str` fields `id`, `run_id`, `short_id`, `name`
- default: none
- required: true
- meaning: `id` is the container id and the row's reconciliation key; `run_id` is the telemetry key, which for a native run *is* the run and for a docker run is whatever id it pushed; `short_id` is the first four characters of the container id, or `----`; `name` is the sort tiebreaker.

### field-row-repository

- type: `str`
- default: `—`
- required: true
- meaning: the compact repository identity — `{repo_name}@{repo_branch}`, falling back to `repo_name`, then to an em dash. The same label the status bar counts distinct values of.

### field-row-type

- type: `str` `type` plus `int` `type_hue`
- default: none
- required: true
- meaning: the workflow type and a stable hue derived from it, so a new kind of workflow gets its own consistent chip color with no CSS change. Types with a fixed look in the stylesheet override the hue.

### field-row-state

- type: `str`, one of the [workflow state](concepts/workflow-state.md) values
- default: none
- required: true
- meaning: lifecycle state. Drives the state dot, the `blocked` row class, and rank 0.

### field-row-liveness

- type: `str` `live` (`live` | `dead` | `done` | `unknown`), `str` `live_label`, `float` `silence_s`
- default: none
- required: true
- meaning: process liveness from telemetry, its display label, and the raw seconds of observed silence. `live_label` is empty for `unknown`, because a run that never reported must not be labelled as anything.

### field-row-progress

- type: `str` `node`, `float` `node_elapsed_s`, `float` `turn_idle_s`, `str` `mini`, `str` `activity`
- default: `""` / `0.0`
- required: true
- meaning: where the run is and whether being there is normal. `mini` is the pre-formatted at-a-glance line — how long the node has been open, and agent idle time once it exceeds a minute.

### field-row-doing

- type: `str`
- default: `""`
- required: true
- meaning: the one line the row shows under its title, resolved gate-path → exit-hint → activity → node.

### field-row-gate

- type: `str` `question`, `str` `gate_path`, `int` `gate_count`
- default: `""` / `""` / `0`
- required: true
- meaning: the first open gate's path, how many are open, and — only when blocked — the [run question preview](concepts/run-question-preview.md).

### field-row-exit

- type: `int | null` `exit_code`, `str` `exit_hint`
- default: `null` / `""`
- required: true
- meaning: the terminal status. `exit_hint` is `exited {code}` only for a finished run with a known code, and empty otherwise.

### field-row-process

- type: `int | null` `pid`, `bool` `native`
- default: `null` / `false`
- required: true
- meaning: how the run is hosted. A native run is a local process with a pid; a docker run is a container.

### field-row-rank

- type: `int`, `0`–`3`
- default: none
- required: true
- meaning: the attention rank the list sorts on. It travels to the client so a merged single-run delta re-sorts by the server's own key.

## Methods

### method-fleet-rows

- sig: `fleet_rows(workflows: list[WorkflowContainer], query: str = "", now: float | None = None) -> list[dict[str, Any]]`
- abstract: false
- raises: none intentionally raised for empty, unmatched, or partially populated snapshots.
- code: groom/groom/projection.py::fleet_rows
- step: Resolve the clock once, so every row in the list is labelled against the same instant.
- step: Project each workflow that satisfies the query, looking its telemetry up from the hot cache by run id.
- step: Sort by `(rank, name)`.
- step: Return the list; no fallback, no partial result, no error channel.

### method-run-row

- sig: `run_row(wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None) -> dict[str, Any]`
- abstract: false
- raises: none intentionally raised for a workflow with or without gates, telemetry, or an exit code.
- code: groom/groom/projection.py::run_row
- step: Sort the workflow's open gates by file path and take the first, if any.
- step: Derive liveness from telemetry and the clock, and the exit hint from state and exit code.
- step: Resolve the `doing` line gate-path → exit-hint → activity → node.
- step: Attach the question preview only when blocked with a gate.
- step: Compute the rank and return the flat row.

### method-match-fleet-query

- sig: `matches(wf: WorkflowContainer, query: str) -> bool`
- abstract: false
- raises: none intentionally raised for missing optional text fields.
- code: groom/groom/projection.py::matches
- step: Return true immediately for an empty query, without reading any haystack.
- step: Lowercase the query and each documented haystack; a missing value compares as the empty string.
- step: Return true when any haystack contains the query as a substring.

### method-run-liveness

- sig: `liveness(wf: WorkflowContainer, tel: RunTelemetry | None, now: float) -> tuple[str, str]`
- abstract: false
- raises: none.
- code: groom/groom/projection.py::liveness
- step: Without telemetry, fall back to the container: `done`/`ended` when the workflow is finished, else `unknown` with an empty label — a run that never reported must not be guessed about.
- step: Return `done` when this session's telemetry reports a terminal, labelled with the terminal reason.
- step: Return `live`/`alive` when observed silence is within the server-side liveness window, whatever the container says.
- step: Otherwise return `dead` with a `silent {duration}` label.

### method-fleet-rank

- sig: `fleet_rank(wf: WorkflowContainer, live_cls: str) -> int`
- abstract: false
- raises: none.
- code: groom/groom/projection.py::fleet_rank
- step: Blocked is 0, whatever its liveness — it is waiting on the operator.
- step: Finished, or liveness `done`, is 3.
- step: Otherwise 1 when liveness is `live`, else 2.

### method-repository-label

- sig: `repo_label(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for missing repository name or branch.
- code: groom/groom/projection.py::repo_label
- step: Return `{repo_name}@{repo_branch}` when a branch is known.
- step: Return `repo_name` when it is not.
- step: Return the em dash placeholder when neither is set.

### method-short-run-id

- sig: `short_id(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for empty or short container ids.
- code: groom/groom/projection.py::short_id
- step: Return the first four characters of the container id, whole if it is shorter.
- step: Return `----` when the id is empty. The `#` prefix is the row component's, not this value's.

### method-exit-hint

- sig: `exit_hint(wf: WorkflowContainer) -> str`
- abstract: false
- raises: none intentionally raised for live, code-less, or non-zero-code workflows.
- code: groom/groom/projection.py::exit_hint
- verify: groom/tests/test_projection.py::test_exit_hint_only_on_finished_with_a_code
- step: Return the empty string unless the workflow is finished and its exit code is known.
- step: Otherwise return `exited {code}`. Classifying zero as success and non-zero as failure is the row component's styling decision, made from `exit_code`.

### method-row-mini

- sig: `row_mini(tel: RunTelemetry | None) -> str`
- abstract: false
- raises: none.
- code: groom/groom/projection.py::row_mini
- step: Return the empty string without telemetry.
- step: Add `in node {duration}` when the node has a measured elapsed time.
- step: Add `agent idle {duration}` only past a minute, so ordinary turn latency does not read as a stall.
- step: Join the parts with a middot separator.

### method-type-hue

- sig: `type_hue(workflow_type: str) -> int`
- abstract: false
- raises: none.
- code: groom/groom/projection.py::type_hue
- step: Fold the type string into a stable value in `0`–`359` and return it, so an unknown workflow type is still visually distinct without a stylesheet change.

## Algorithms

### algorithm-project-the-fleet

- step: Receive the workflow snapshot, the optional query, and the clock.
- step: Drop workflows the query excludes; every remaining one becomes a row regardless of state or gates.
- step: For each, look up telemetry by run id, derive liveness against the clock, and flatten identity, repository, type, progress, gate, exit, and process fields into one JSON object.
- step: Sort by rank, then name.
- step: Hand the array to [state message](concepts/groom-projection-module.md#method-state-message), which pairs it with fleet-wide status counts.

### algorithm-render-and-merge-a-row

- step: The client keys each row by container id, so a re-render reuses the same DOM node and does not disturb focus or scroll.
- step: A row draws the state dot from `state`, the type badge from `type` and `type_hue`, the liveness chip from `live` and `live_label`, the `doing` line, the `mini` line, and the question preview when present.
- step: A single-run push replaces the row with the same id — or appends when the run is new — then re-sorts by `(rank, name)`, which is the same order the server projected.

## Failure Semantics

- Unsupported workflow state: rank and status counting index the documented state enum directly; a state outside it is outside the contract and fails rather than falling back to a display bucket.
- Missing telemetry: a supported input, not an error. The row reports liveness `unknown`, zero durations, and an empty `mini`.
- Malformed gate record: gate projection expects text `file_path` and `question` values; anything else is outside the contract and fails as ordinary Python attribute or string operations fail.
- Query input: the supported type is `str`; `None` and non-string values are outside the contract even though the empty-string default covers unfiltered projection.
- Empty and unmatched snapshots: an empty workflow list or a query matching nothing returns an empty array. The empty-versus-loading distinction is the client's, made from the scanning flag.
- Delegated exceptions: this concept defines no domain-specific error object, partial result, or status code. It performs no registry rollback, websocket send, HTTP response construction, or gate write of its own.

## Invariants

- whole-fleet: every workflow in the supplied snapshot produces a row unless the query excludes it. Nothing is hidden for lacking gates, telemetry, or a live process.
- stable-order: the same snapshot and clock always produce the same order, so a tick never reshuffles the list.
- fleet-counts: filtering the rows never redefines the status-bar totals, which stay global to the registry.
- one-row-shape: the row in a full-state payload and the row in a single-run delta are the same object shape, so the client has one merge rule.
- data-not-markup: no field is HTML, and no field's safety depends on an escape call being remembered.
- answer-lifecycle: answering a run's last gate does not remove it from the fleet — it drops the gate fields and re-ranks the row on the next projection.
- row-accessibility: rows are native `<button type="button">` elements named by their visible text and activatable with Enter or Space; keyboard row movement also exists as separate global `j`/`k` behavior on the dashboard.
