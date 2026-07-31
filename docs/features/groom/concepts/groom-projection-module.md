---
type: concept
slug: groom-projection-module
title: Groom projection module
---
# Groom projection module

The Groom projection module is the single place a [workflow container](workflow-container.md), [gate info](gate-info.md), or telemetry record becomes a wire shape. The browser renders; the server projects. Every payload the [groom server](../http/groom.md) hands a dashboard tab — pushed on the websocket or pulled from `GET /api/state` and the panel endpoints — is built here.

That "single place" is the point rather than a tidiness preference. Groom has two delivery paths to the same tab: the socket pushes state on every change and on the live clock, and HTTP carries the full-state resync a tab falls back to when its socket goes quiet or dies. If those paths projected separately they would drift, and the drift would be invisible — the resync path only runs when something has already gone wrong. Both call the functions here, so a tab that resynced and a tab that was pushed to are holding byte-identical JSON and feed it through one `applyState()` in the [dashboard client store](dashboard-client-store.md).

Nothing here emits markup, reads a request, opens a socket, or touches Docker. It is pure `(dataclasses, clock) -> dict`, which is also what makes the shapes cheap to assert: the projection tests build containers in memory and compare dicts, with no server running.

Labels that encode a *judgement* — `alive` versus `silent 4m`, the fleet's sort rank, an exit hint — are computed here rather than in the browser. They are policy, they are thresholded against server-side constants, and two implementations of them would disagree. Raw numbers ride along beside every label so the client can re-format without re-deciding.

- code: groom/groom/projection.py
- refs: [workflow container](workflow-container.md), [gate info](gate-info.md), [dashboard state payload](../dashboard-state-payload.md), [runs fleet view](../runs-fleet-view.md), [dashboard client store](dashboard-client-store.md), [dashboard shell broadcaster](dashboard-shell-broadcaster.md), [run watch registry](run-watch-registry.md)
- verify: groom/tests/test_projection.py::test_state_message_is_json_serializable
- verify: groom/tests/test_projection.py::test_run_message_row_matches_the_same_row_in_the_state_message
- verify: groom/tests/test_projection.py::test_detail_message_matches_the_fetched_detail
- verify: groom/tests/test_projection.py::test_gate_question_travels_as_data_not_markup

## Contract

- purpose: turn groom's in-memory dataclasses into the JSON shapes the dashboard consumes, once, for both delivery paths.
- purity: every public function is a pure function of its arguments plus module state reads (`state.RUNS`, `store` thresholds) and an injectable clock; none performs I/O, mutation, or rendering.
- clock injection: every time-dependent function takes `now: float | None` and defaults to `time.time()` when omitted, so a test can pin the clock and assert a label instead of a range.
- output type: plain JSON-serializable `dict`/`list` built from `str`, `int`, `float`, `bool`, and `None`; no dataclass, enum, `datetime`, or set escapes into a payload.
- no markup: the module emits data only. A gate's question travels as its text, and the client decides how to display it — which is what stopped operator-supplied question text from ever being interpolated into server-rendered HTML.
- discriminator: every pushed message carries a `type` field — `state`, `run`, `detail` — and the client dispatches on it. Panel-endpoint payloads are bodies of a known request and carry no discriminator.
- label + number: a projected value that a human reads as a judgement is accompanied by the raw input it was derived from, so re-formatting in the browser never requires re-deciding.
- thresholds: liveness classification reads `store.LIVE_AFTER_S`; the log trail is capped at `LOG_TRAIL_LIMIT`; severity coloring comes from `SEVERITY_CLASS`. All three are server-side policy and are not duplicated in the client.
- ordering: fleet order is blocked, then alive, then presumed-dead, then finished, with ties broken by name so the list does not shuffle on a tick.
- filtering: `state_message` accepts a query that filters the run list; the fleet-wide counts in `status` stay fleet-wide regardless, because a filtered count would misreport the fleet.

## Callers

- fleet broadcast and resync: [dashboard shell broadcaster](dashboard-shell-broadcaster.md) and [get dashboard state](../http/groom.md#get-dashboard-state) both call `state_message`, which is what makes push and resync the same payload.
- websocket handshake: the [run dashboard websocket session](../http/groom.md#run-dashboard-websocket-session) sends `state_message` as its first frame, so a newly opened tab starts from the same snapshot a resync would have given it.
- addressed detail: the detail push path projects `detail_message` for the runs named by the [run watch registry](run-watch-registry.md); the [get run detail](../http/groom.md#get-run-detail) endpoint returns the same `run_detail` body for a tab that fetched it directly.
- panels: the repository picker, file viewer, and telemetry endpoints call `repo_entries`, `file_lang`, and `traces_view`.

## Fields

### field-state-order

- type: `dict[WorkflowState, int]`
- default: blocked 0, running 1, idle 2, finished 3
- required: true
- code: groom/groom/projection.py::STATE_ORDER
- meaning: the primary sort key behind fleet order — work that needs an operator sorts above work that does not.

### field-log-trail-limit

- type: `int`
- default: 60
- required: true
- code: groom/groom/projection.py::LOG_TRAIL_LIMIT
- meaning: how many log lines a detail pane's trail carries, newest first. The same constant bounds the durable query, so the payload size is decided once.

### field-severity-class

- type: `dict[str, str]`
- default: `FATAL`/`ERROR` → `bad`, `WARNING` → `warn`
- required: true
- code: groom/groom/projection.py::SEVERITY_CLASS
- meaning: which log severities earn a color class in the trail; everything else reads plain.

### field-ext-lang

- type: `dict[str, str]`
- default: a fixed extension → highlight.js language table
- required: true
- code: groom/groom/projection.py::EXT_LANG
- meaning: the language hint the file viewer passes to highlight.js. An unmapped extension projects `""`, which the viewer reads as "auto-detect".

## Methods

### method-state-message

- sig: `state_message(workflows: list[WorkflowContainer], query: str = "", now: float | None = None) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::state_message
- step: Resolve the clock, defaulting to wall time.
- step: Project the filtered fleet through `fleet_rows` in display order.
- step: Project the unfiltered fleet through `status_bar` so counts stay fleet-wide.
- step: Return `{"type": "state", "ts", "scanning", "runs", "status"}` — the [dashboard state payload](../dashboard-state-payload.md).

### method-run-message

- sig: `run_message(wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::run_message
- step: Project one run through the same `run_row` used for an entry in `state.runs`.
- step: Return `{"type": "run", "ts", "run"}`, which the client merges into its existing list in place rather than replacing the whole fleet — so the other rows keep their DOM nodes, and their focus.

### method-detail-message

- sig: `detail_message(wf, tel=None, facts=None, logs=None, now=None) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::detail_message
- step: Project the full `run_detail` body — gates, head, metrics, log trail — not a reduced slice.
- step: Return `{"type": "detail", "ts", "id", "detail"}`, addressed to the tabs in the [run watch registry](run-watch-registry.md).
- step: Carry the whole body deliberately: the client reconciles it against a keyed component tree, so a gate that opened or closed appears without a round trip while the answer textarea keeps its DOM node and therefore a half-typed answer. Under the old fragment swap that was impossible, which is why the pushed refresh used to stop short of the form.

### method-run-detail

- sig: `run_detail(wf, tel=None, facts=None, logs=None, now=None) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::run_detail
- step: Project identity (`id`, `run_id`, `state`, `node`), every open gate through `gate_dict`, and the live slice (`head`, `metrics`, `log`).
- step: Return the same body both the pushed `detail` message and the detail fetch carry, so a subscription and a fetch cannot disagree.

### method-fleet-rows

- sig: `fleet_rows(workflows: list[WorkflowContainer], query: str = "", now: float | None = None) -> list[dict]`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::fleet_rows
- step: Project each matching container through `run_row`, attaching its telemetry from the hot cache.
- step: Sort by `(rank, name)` so the order is stable across ticks.

### method-status-bar

- sig: `status_bar(workflows: list[WorkflowContainer]) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::status_bar
- step: Count containers per state, count distinct repositories, and count workers; return all three as fleet-wide totals that no query narrows.

### method-repo-entries

- sig: `repo_entries(entries: list[tuple[WorkflowContainer, list[str]]]) -> list[dict]`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::repo_entries
- step: Emit one group per container carrying the checkouts found on its volume — grouped rather than flat because that is the shape the server actually has, and because a picker row's label is derived from both halves.
- step: Give a workflow with no discoverable repository a single volume-root entry so it can still be browsed.

### method-traces-view

- sig: `traces_view(summaries: list[dict], spans: list[dict], runs: dict[str, RunTelemetry], live_ids: set[str] = frozenset(), now: float | None = None, connected_only: bool = True) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::traces_view
- step: Project a per-run summary strip (with any fired alert rules) above the filtered span table.
- step: Pass `live_ids` — the runs the durable store sees beating now — through to every card, so a run absent from the hot cache (a groom that just restarted) is still reported as running.
- step: Drop every card that is not `live` unless `connected_only` is false, so the pane shows what is running rather than two weeks of retained history, and reuse the same `live` value the card already carries rather than a second notion of connectedness.
- step: Drop the spans of the runs that were hidden, so the table never lists nodes of a run absent from the strip above it.
- step: Stay a pull view: telemetry is fetched on demand, and only the alerts are pushed.

### method-run-card

- sig: `run_card(summary: dict, tel: RunTelemetry | None, live_ids: set[str] = frozenset(), now: float | None = None) -> dict`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::run_card
- step: Derive `live` from the hot cache when this run is in it, and from `live_ids` otherwise — never from the span history in `summary`, which can only say what a run has already done.
- step: Report `doing` as the activity the run stamped, else its live node, so the pane reads as work in progress rather than a list of opaque run ids.

### method-is-live

- sig: `is_live(tel: RunTelemetry | None, now: float) -> bool`
- abstract: false
- raises: none.
- code: groom/groom/projection.py::is_live
- step: Answer the one liveness question — is this run emitting right now — from telemetry recency alone.
- step: Report not-running when this session's terminal has landed, or when nothing has been heard inside the liveness window; an earlier session's terminal does not count, because it is cleared as soon as a newer signal arrives.

### method-file-lang

- sig: `file_lang(path: str) -> str`
- abstract: false
- raises: none intentionally raised.
- code: groom/groom/projection.py::file_lang
- step: Match the whole filename first for the extensionless files that still have a grammar (`Dockerfile`, `Makefile`), then the extension against `EXT_LANG`, else return `""`.

## Algorithms

### algorithm-one-shape-two-paths

- step: A state change or the live clock reaches the [dashboard shell broadcaster](dashboard-shell-broadcaster.md); it calls `state_message` and broadcasts the result.
- step: A tab whose socket has gone quiet calls `GET /api/state`; the handler calls the same `state_message` and returns the result as the response body.
- step: Both payloads reach the client's single `applyState()`, so the resync path is not a second rendering path that can rot unobserved — it is the only path, reached a different way.

## Failure Semantics

- Missing telemetry: a container with no cached `RunTelemetry` projects `unknown` liveness and empty metrics rather than raising or omitting the row.
- Missing durable facts: `run_detail` accepts `facts=None` and `logs=None` and projects the run without them, which is what lets a detail be pushed before the two SQLite reads have happened.
- Absent extension mapping: `file_lang` returns `""`, deferring to highlight.js auto-detection rather than guessing.
- No error type of its own: the module raises nothing on groom's behalf. A malformed dataclass surfaces as an ordinary attribute or key error at the call site.
