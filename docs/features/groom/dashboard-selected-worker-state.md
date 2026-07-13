---
type: format
slug: dashboard-selected-worker-state
title: Dashboard selected worker state
---
# Dashboard selected worker state

Dashboard selected worker state is the browser-local selected workflow id on the [groom dashboard](gui/screens/groom-dashboard.md). It is written by [select inbox worker row](gui/screens/groom-dashboard.md#select-inbox-worker-row), [keyboard select inbox worker row](gui/screens/groom-dashboard.md#keyboard-select-inbox-worker-row), and [select command palette result](gui/screens/groom-dashboard.md#select-command-palette-result); read by the [dashboard inbox selection applier](concepts/dashboard-inbox-selection-applier.md), the selected-worker detail fetch, and the `groom:answered` success handler; and used to keep row highlighting and the `#detail` pane scoped to one [workflow container](concepts/workflow-container.md) without mutating server workflow state.

- file: not an on-disk artifact; this is a closure-local JavaScript variable retained for the lifetime of the loaded dashboard page.
- code: groom/groom/templates/dashboard.html::selected

## Contract

- producer: the shared dashboard `select(id)` handler replaces the current value with the id read from an inbox row `data-worker-id`, command palette result `data-id`, or keyboard-selected row `data-worker-id`.
- consumers: the same selection handler immediately fetches [GET /worker/{container_id}](http/groom.md#get-worker-detail); the [dashboard inbox selection applier](concepts/dashboard-inbox-selection-applier.md) compares current rows against the value; the keyboard movement handler uses it to find the current row index; the `groom:answered` listener compares successful answer event ids against it before refreshing detail.
- lifetime: initialized when the dashboard script loads, retained across inbox/status out-of-band websocket swaps, search-result swaps, activity-mode switches, repository-menu use, command-palette open/close cycles, file/diff pane loads, and successful or failed answer broadcasts until another worker selection overwrites it or the page unloads.
- absent state: `null` means no worker has been selected in this loaded page; row-selection styling is cleared for all current `[data-worker-id]` elements and keyboard `j`/`k` movement starts from the first rendered inbox row.
- selected state: any string value is treated as the selected worker id exactly as stored, without trimming, case normalization, empty-string rejection, existence checking, or server-registry validation.
- stale state: if the stored id is no longer present in the current inbox rows or server registry, the value remains stored; row styling clears during selection application, keyboard movement falls back to the first rendered row, and the detail fetch may render the endpoint's unknown-worker fragment.
- server effect: none directly; this state only scopes browser DOM class updates and later HTTP GET requests, and never writes workflow records, gate records, answer files, sidecar state, websocket queues, browser storage, or URL state.
- accessibility effect: the state is reflected only through the visual `selected` CSS class and replacement detail pane; it is not exposed as focus, `aria-selected`, `aria-current`, live-region text, or a route change.

## Fields

### field-selected-worker-id

- type: `str | null`
- default: `null`
- required: false before selection; true for a selected-worker detail request after an inbox row, palette result, or keyboard row movement selects a worker.
- meaning: workflow container id currently selected in the dashboard page; string values are compared exactly against DOM `data-worker-id` values and URL-encoded into `/worker/{container_id}` detail requests.
- source: copied from `dataset.workerId` on a selected inbox row or from `dataset.id` on a selected command-palette result.
- write rule: replaced wholesale by every call to the shared `select(id)` handler before row classes are reconciled and before the worker-detail request is issued.
- read rule: read synchronously by selection styling, keyboard row movement, and answered-event refresh logic; no first-party code serializes it to local storage, session storage, cookies, query parameters, or websocket frames.

### field-selected-row-class

- type: `CSS class token "selected" derived from field-selected-worker-id`
- default: absent on all worker-bearing elements when selected worker id is `null` or not represented in the current DOM.
- required: false; present only on current `[data-worker-id]` elements whose `dataset.workerId` exactly equals the selected worker id.
- meaning: visible row-selection marker derived from selected worker state by the [dashboard inbox selection applier](concepts/dashboard-inbox-selection-applier.md); it is a projection of the selected id, not a separate source of truth.
- mutation rule: recalculated for every current `[data-worker-id]` element whenever selection is applied; out-of-band inbox swaps require reapplication because new row elements do not preserve prior class objects.
- accessibility rule: does not create keyboard focus, a semantic selected state, or an accessible announcement; it is visual styling only.

### field-selected-detail-scope

- type: `HTTP detail request target derived from field-selected-worker-id`
- default: none before selection.
- required: true for each detail fetch triggered by selection or same-worker answered-event refresh.
- meaning: the selected worker id after `encodeURIComponent` becomes the `{container_id}` segment in `GET /worker/{container_id}`, whose response replaces only `#detail` with selected-worker detail HTML.
- refresh rule: selecting a different worker replaces this scope immediately; a successful `groom:answered` event refreshes detail only when the event detail id exactly equals the current selected worker id.
- preservation rule: websocket shell broadcasts, search swaps, repository selection, Files/Diff activity changes, and refresh scans do not replace `#detail` through this state unless they also lead to an explicit selected-worker fetch.
