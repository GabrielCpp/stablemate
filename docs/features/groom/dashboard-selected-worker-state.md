---
type: format
slug: dashboard-selected-worker-state
title: Dashboard selected worker state
---
# Dashboard selected worker state

Dashboard selected worker state is the browser-local id of the open run on the [groom dashboard](gui/screens/groom-dashboard.md) — the `selected` field of the [dashboard client store](concepts/dashboard-client-store.md). It is written by the [dashboard run selector](concepts/dashboard-run-selector.md), whichever way the operator got there; it is read by the fleet list to mark the current row, by the detail pane to decide what it is showing, by keyboard row movement to find where it is, and by the pushed-detail handler to decide whether an arriving frame is about the run this tab has open. It scopes browser rendering and requests to one [workflow container](concepts/workflow-container.md) and mutates no server state.

The id is the only selection state stored. Everything visible about selection — the row's class, its `aria-current`, the pane's contents, which run this tab watches — is derived from it at render time or requested from it, so there is no second copy to keep in step. That is what removed the reconciler the fragment era needed: a re-rendered row cannot disagree with the selection, because it is rendered *from* it.

- file: not an on-disk artifact; this is one field of the browser-local store, retained for the lifetime of the loaded dashboard page.
- code: groom/groom/assets/dashboard.js::select
- code: groom/groom/assets/dashboard.js::Fleet
- code: groom/groom/assets/dashboard.js::onDetail
- refs: [dashboard client store](concepts/dashboard-client-store.md), [dashboard run selector](concepts/dashboard-run-selector.md), [run watch registry](concepts/run-watch-registry.md)

## Contract

- producer: the run selector replaces the current value with the id read from a fleet row's `data-worker-id` or from a command-palette result. Nothing else writes it.
- paired write: it is always written together with a `null` detail, so a render never pairs a new selection with the previous run's pane.
- consumers: the fleet list compares each row against it; the detail pane renders from it; the run selector fetches [GET /worker/{container_id}](http/groom.md#get-run-detail) with it and sends this tab's watch subscription for it; the keyboard row-movement handler uses it to find the current row index; the pushed-detail handler drops any `detail` frame whose id does not equal it.
- lifetime: `null` when the dashboard module loads, then retained across fleet ticks, resyncs, connection-state changes, mode switches, repository-menu use, palette open/close cycles, pane loads, and answer broadcasts, until another selection overwrites it or the page unloads.
- absent state: `null` means nothing is open in this tab. No row is marked current, the detail pane renders its own prompt to select a run, and keyboard row movement starts from the first rendered row.
- selected state: any string is treated as the id exactly as stored — no trimming, case normalization, empty-string rejection, existence check, or registry validation happens in the browser.
- stale state: an id no longer in the fleet stays stored. No row matches it, so none is marked current, and the detail fetch renders the endpoint's not-found body. The selection is not cleared, because clearing it would hide why the pane went empty.
- subscription coupling: the value is also what this tab is subscribed to on the socket. The server's [run watch registry](concepts/run-watch-registry.md) holds the server-side half; a reconnect re-sends the subscription from this value, which is why the tab's own copy is the authority and the socket's is the cache.
- not persisted: never serialized to local storage, session storage, cookies, query parameters, or the URL. A reload starts with nothing open.
- not pushed: no server message writes it. Pushes are filtered *by* it; they do not change it.
- server effect: none beyond the watch subscription. It writes no workflow record, gate, answer file, or sidecar state.
- accessibility effect: the open row carries `aria-current="true"`, and every other row omits the attribute entirely rather than carrying `"false"`, so exactly one row is announced as current.

## Fields

### field-selected-worker-id

- type: `str | null`
- default: `null`
- required: false before a selection; required for every run-scoped request after one.
- wire-location: browser-internal; the store's `selected` field.
- meaning: the workflow container id of the open run. It is compared against rendered rows, URL-encoded into `/worker/{container_id}`, sent as the watch command's target, and matched against the id on every pushed detail frame.
- source: the chosen fleet row's `data-worker-id`, or the chosen palette result's id.
- write rule: replaced wholesale by the run selector, in the same store write that clears the detail pane.
- read rule: read synchronously during render and by the frame dispatcher; no first-party code serializes it anywhere.

### field-selected-row-marking

- type: the `selected` class and `aria-current="true"`, derived from [field-selected-worker-id](#field-selected-worker-id)
- default: absent on every row when nothing is selected or when no rendered row matches.
- required: false; present on at most one row.
- meaning: the visible and announced marking of the open row. It is a render-time projection of the id, not stored state and not a second source of truth.
- mutation rule: recomputed on every render of the fleet list. There is no reapplication step after a push, because a pushed fleet is rendered through the same component that reads the selection.
- accessibility rule: `aria-current` is the semantic half and the class is the visual half. Neither moves focus; the row keeps focus where the operator left it.

### field-selected-detail-scope

- type: the run-detail request target derived from [field-selected-worker-id](#field-selected-worker-id)
- default: none before a selection.
- required: true for the one detail fetch each selection issues.
- meaning: the id, `encodeURIComponent`-escaped, as the `{container_id}` segment of [GET /worker/{container_id}](http/groom.md#get-run-detail), whose JSON body becomes the store's `detail`.
- refresh rule: after the initial fetch, the pane is refreshed by pushed detail frames for the watched run rather than by re-fetching. A successful answer is confirmed by a [dashboard answered message](dashboard-answered-message.md) that triggers no request at all, because the detail push arrived with it.
- preservation rule: fleet broadcasts, resyncs, repository selection, mode changes, and refresh scans do not touch the detail pane; only a new selection or a detail push for the watched run replaces it.
