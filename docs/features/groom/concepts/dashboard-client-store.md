---
type: concept
slug: dashboard-client-store
title: Dashboard client store
---
# Dashboard client store

Dashboard client store is the [groom dashboard](../gui/screens/groom-dashboard.md)'s single client-side snapshot: one plain object holding the fleet, the connection phase, the open run's detail, the active mode, and each panel's own slice. Every Preact island subscribes to it, and every delivery path — a pushed socket frame, a [dashboard resync poller](dashboard-resync-poller.md) response, a panel fetch — writes into it and nowhere else.

It is deliberately not a per-component `useState`. The socket is a singleton and the islands read overlapping slices of the same truth: the fleet list, the status bar, and the command palette are three views of one `runs` array. Keeping the state outside the component tree makes the components pure functions of it, which is what allows the whole page to be re-rendered from a single 5-second push without any island owning a private copy that could disagree.

The store is also the boundary that decides what is fleet-wide and what is per-tab. `runs`, `status`, `scanning`, and `conn` come from the server. `mode`, `query`, `repo`, `files`, `diff`, `traces`, and `palette` never leave the browser — the server has no idea which pane a tab is looking at, and does not need one. The single exception is `selected`, which is echoed to the server as a subscription in the [run watch registry](run-watch-registry.md) because a pushed detail has to be addressed somewhere.

- code: groom/groom/assets/dashboard.js::store
- code: groom/groom/assets/dashboard.js::applyState
- code: groom/groom/assets/dashboard.js::applyRun
- code: groom/groom/assets/dashboard.js::setIn
- code: groom/groom/assets/dashboard.js::useStore
- refs: [dashboard state payload](../dashboard-state-payload.md), [runs fleet view](../runs-fleet-view.md), [groom projection module](groom-projection-module.md), [dashboard connection state machine](dashboard-connection-state-machine.md), [dashboard resync poller](dashboard-resync-poller.md), [run watch registry](run-watch-registry.md)
- verify: groom/tests/test_dashboard_client.py::test_the_client_module_parses
- verify: groom/tests/test_dashboard_client.py::test_every_endpoint_is_read_as_json
- verify: groom/tests/test_dashboard_client.py::test_no_fragment_swapping_survives
- verify: groom/tests/test_dashboard_client.py::test_the_only_markup_the_client_sets_comes_from_a_sanitizer_or_a_renderer

## Contract

- purpose: hold one snapshot of everything the dashboard displays, and be the only place any of it is written.
- shape: a flat object of named slices. The top level is shallow-merged; nested slices are replaced wholesale through [set in slice](#method-set-in), so a panel updating its own key can never clobber another's.
- subscription: islands call [use store](#method-use-store), which subscribes on mount and unsubscribes on unmount; every `set` notifies every listener with the new snapshot.
- immutability by convention: `set` builds a new top-level object rather than mutating in place, so a component comparing snapshots sees a new identity.
- single fleet entry point: `applyState()` is the only writer of `runs`, `status`, and `scanning`, and both delivery paths call it. This is the invariant that keeps a resynced tab and a pushed tab identical.
- delta merge: `applyRun()` merges one row in place by id and re-sorts by `(rank, name)` — the same order the server projected — so the other rows are not re-created and do not lose focus.
- keyed reconciliation: rows are keyed by run id and gate blocks by gate file path. That is what preserves focus, scroll position, and — because Preact then reuses the same `<textarea>` DOM node — a half-typed answer across a 5-second push.
- detail ownership: `detail` is written by a pushed `detail` frame and by the one fetch a selection issues; the pushed frame is ignored unless its id matches the current selection, so a stale push for a run the operator has moved off cannot overwrite the pane.
- selection race: `select()` stamps a sequence number and applies its fetch result only if it is still the newest selection *and* no push has already filled the pane. Whichever of the two arrives first wins and the other is dropped, so fast clicking cannot land the wrong run's detail.
- markup boundary: the store holds data, never markup. The only strings that ever reach `innerHTML` anywhere in the client are the outputs of DOMPurify, diff2html, and highlight.js.
- panel laziness: per-selection panels are fetched when their mode becomes active, not held current in the background — the server does not push files, diffs, or traces.
- islands: each component is mounted into an id the static shell already ships, so the live-region, landmark, and label attributes live on elements that outlive every update.

## Fields

### field-runs

- type: `array` of run rows, as projected by [groom projection module](groom-projection-module.md)
- default: `[]`
- required: true
- meaning: the fleet in display order. Written only by `applyState` and `applyRun`; read by the fleet list, the status counts, and the palette.

### field-status

- type: `{counts, repos, workers}`
- default: `{counts: {}, repos: 0, workers: 0}`
- required: true
- meaning: the fleet-wide totals in the status bar. Fleet-wide even when a query is filtering the visible list.

### field-scanning

- type: `boolean`
- default: `true`
- required: true
- meaning: whether discovery is still in flight. The list renders a spinner rather than the "no workers" empty state, so a not-yet-scanned fleet does not read as finished-and-empty.

### field-conn

- type: `{phase, resyncing}`
- default: `{phase: "connecting", resyncing: false}`
- required: true
- meaning: the connection phase from the [dashboard connection state machine](dashboard-connection-state-machine.md), rendered by the connection chip.

### field-query

- type: `string`
- default: `""`
- required: true
- meaning: the client-side filter over `runs`. Per-tab; never sent to the server by the fleet view.

### field-selected

- type: `string | null` (a container id)
- default: `null`
- required: false
- meaning: the run whose detail pane is open. The one piece of per-tab state echoed to the server, as a `watch` subscription.

### field-detail

- type: `object | null` — a `run_detail` body
- default: `null`
- required: false
- meaning: the open run's gates, head, metrics, and log trail.

### field-mode

- type: one of `runs`, `files`, `diff`, `telemetry`, `settings`
- default: `runs`
- required: true
- meaning: which pane the activity rail has active. Mirrored onto `.app[data-mode]` so CSS can show the right pane, and onto each rail button's `aria-pressed`.

### field-repo

- type: `{loading, groups, query, active, container, dir, label}`
- default: nothing loaded, no container selected
- required: true
- meaning: the repository picker's own state — the containers and checkouts offered, and the one currently chosen for the files and diff panes.

### field-files

- type: `{status, paths, path, view: {status, path, content, lang}}`
- default: `idle`, nothing loaded
- required: true
- meaning: the file browser's path list and the currently open file's content and language hint.

### field-diff

- type: `{status, files, idx}`
- default: `idle`, no files, `idx: -1`
- required: true
- meaning: the working-tree diff's per-file list and which file is shown.

### field-traces

- type: `{status, runs, spans}`
- default: `idle`, empty
- required: true
- meaning: the telemetry pane's run summary strip and span table. A pull view — only alerts are pushed.

### field-palette

- type: `{open, query, active}`
- default: closed
- required: true
- meaning: the command palette's open state and keyboard cursor; its results are derived from `runs` rather than stored.

## Methods

### method-apply-state

- sig: `applyState(msg) -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::applyState
- step: Write `runs`, `status`, and `scanning` from the payload, defaulting each to what is already held rather than to nothing.
- step: Notify every subscriber once, with one new snapshot.
- step: Be the only writer of these three keys, whether the payload arrived on the socket or from `GET /api/state`.

### method-apply-run

- sig: `applyRun(msg) -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::applyRun
- step: Ignore a message with no `run` body.
- step: Copy the current list, replace the row with the same id, or append it when the run is new.
- step: Re-sort by `(rank, name)` — the server's own order — and write the list back.

### method-set-in

- sig: `setIn(key, patch) -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::setIn
- step: Shallow-merge `patch` into the named slice and write the merged slice back as a new object, leaving every other slice untouched.

### method-use-store

- sig: `useStore() -> snapshot`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::useStore
- step: Seed component state with the current snapshot.
- step: Subscribe on mount and return the unsubscribe function as the effect's cleanup.
- step: Return the latest snapshot on every render, so the component is a pure function of store state.

### method-select

- sig: `async select(id) -> void`
- abstract: false
- raises: none; a failed fetch is swallowed.
- code: groom/groom/assets/dashboard.js::select
- step: Bump the selection sequence and write `{selected: id, detail: null}` so the pane visibly changes immediately.
- step: Send the `watch` subscription, which is what makes future changes to this run arrive without polling.
- step: Fetch this run's detail once, for the case where nothing changes soon enough to push.
- step: Apply the fetched body only if this is still the newest selection and no push has already filled the pane; otherwise drop it.
- step: On fetch failure, do nothing — the subscription fills the pane on the next tick.

### method-on-detail

- sig: `onDetail(msg) -> void`
- abstract: false
- raises: none.
- code: groom/groom/assets/dashboard.js::onDetail
- step: Ignore the frame unless its id is the currently selected run.
- step: Replace `detail` with the whole pushed body — gates included — because the keyed component tree makes a full replacement non-destructive.

## Algorithms

### algorithm-one-state-shape-one-render-path

- step: The server projects a `state` payload once, in [groom projection module](groom-projection-module.md).
- step: It travels either as a pushed websocket frame or as the body of `GET /api/state`.
- step: Either way the client calls `applyState()`.
- step: Every island re-renders from the resulting snapshot, keyed so that focus, scroll, and half-typed input survive.
- step: There is therefore no path through which a pushed tab and a resynced tab can display different things.

## Failure Semantics

- Unparseable frame: dropped before it reaches the store; nothing is written and connection recency is not stamped.
- Missing keys in a payload: `applyState` falls back to the existing value for `status` and to an empty list for `runs`, so a partial payload degrades rather than blanking the page.
- Push for an unselected run: `onDetail` returns without writing, so a race between a selection change and an in-flight push cannot show the wrong run's gates.
- Panel fetch failure: each panel writes its own `status: "error"` into its own slice; the fleet, the connection phase, and the other panels are unaffected.
- Store errors: the store has no error state of its own. Anything a listener throws surfaces as an ordinary render error rather than being caught and hidden.
