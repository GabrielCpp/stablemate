---
type: concept
slug: dashboard-inbox-selection-applier
title: Dashboard inbox selection applier
---
# Dashboard inbox selection applier

Dashboard inbox selection applier is the browser-side class reconciler used by [select inbox worker row](../gui/screens/groom-dashboard.md#select-inbox-worker-row), [keyboard select inbox worker row](../gui/screens/groom-dashboard.md#keyboard-select-inbox-worker-row), [select command palette result](../gui/screens/groom-dashboard.md#select-command-palette-result), and websocket/search out-of-band inbox replacements on the [groom dashboard](../gui/screens/groom-dashboard.md). It reads the [dashboard selected worker state](../dashboard-selected-worker-state.md) and makes every currently rendered worker-bearing dashboard element visually agree with that selected id without fetching detail, moving focus, or mutating server state.

- code: groom/groom/templates/dashboard.html::applySelection
- refs: [dashboard selected worker state](../dashboard-selected-worker-state.md), [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row), [command palette result](../gui/screens/groom-dashboard.md#command-palette-result)

## Contract

- purpose: make the dashboard's visible worker-selection styling match the current browser-local selected worker id after row selection, palette selection, keyboard row movement, or an out-of-band inbox replacement.
- input: no formal arguments; reads the closure-local selected worker id held by the dashboard script.
- source state: [dashboard selected worker state](../dashboard-selected-worker-state.md), represented at runtime by the dashboard script's `selected` value, where `null` means no worker is selected and any string value is compared exactly against DOM `data-worker-id` values.
- target set: every element in the current document matching `[data-worker-id]`, not just rows inside `#inbox-list`; in the shipped dashboard this includes server-rendered [inbox worker row](../gui/screens/groom-dashboard.md#inbox-worker-row) elements and excludes generated [command palette result](../gui/screens/groom-dashboard.md#command-palette-result) rows because those use `data-id` instead.
- matching rule: an element is selected exactly when its `dataset.workerId` strictly equals the current selected worker id; empty strings, stale ids, and ids no longer known by the server still participate in the same equality rule.
- output: no return value; completion means all currently matched elements have had their `selected` class reconciled.
- idempotence: repeated calls with the same selected worker id and same DOM produce the same class set.
- empty-state behavior: when no `[data-worker-id]` elements exist, no DOM class changes occur and no error is intentionally raised.
- stale-state behavior: when selected worker state is non-null but no rendered element has that id, the function clears `selected` from every current worker-bearing element and leaves the stored selected id unchanged.
- accessibility effect: the visual `selected` class is the only perceivable selection update; the function does not set focus, `aria-selected`, `aria-current`, live-region text, or any accessible name.
- side effects: mutates only DOM `classList` membership for the `selected` class on worker-bearing elements; it does not issue HTTP requests, websocket messages, htmx swaps, browser navigation, storage writes, notifications, or server mutations.

## Methods

### method-apply-selection

- sig: `applySelection() -> void`
- abstract: false
- raises: none intentionally raised by the dashboard script.
- code: groom/groom/templates/dashboard.html::applySelection

Reconciles the visible selected row class by querying the current document at call time, comparing each worker-bearing element to the selected worker id, and toggling the `selected` class from that comparison result.

#### Effects

- Reads: the closure-local selected worker id set by the shared row-selection handler.
- Reads: the live document collection returned by the selector `[data-worker-id]`.
- For each matched element: reads `element.dataset.workerId` exactly as exposed by the DOM dataset API.
- For each matched element: toggles the `selected` CSS class on when `element.dataset.workerId === selected` and off otherwise.
- Preserves: selected worker id, detail pane HTML, inbox row order, command palette open state, repository selection, activity mode, websocket connection, browser URL, and server workflow registry.
- Calls: no first-party groom symbol; all work is browser DOM selection and class mutation.
