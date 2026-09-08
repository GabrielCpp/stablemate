---
type: concept
slug: dashboard-run-selector
title: Dashboard run selector
---
# Dashboard run selector

Dashboard run selector is the browser-side handler that opens one run. Every way of choosing a run on the [groom dashboard](../gui/screens/groom-dashboard.md) — clicking a fleet row, moving through rows with the keyboard, or picking a command-palette result — ends here. It writes [dashboard selected worker state](../dashboard-selected-worker-state.md), subscribes this tab to that run over the socket, and fetches the detail pane once so the pane is filled immediately rather than up to a tick later.

These are not competing selector implementations and none is preferred. Use a fleet row for the run already visible under the pointer or focus, `j` and `k` to move among the currently rendered fleet rows, and a command-palette result to reach a matching run from any dashboard pane. Each entry path supplies its run id to the same selector: the delegated row handler calls `select(node.dataset.workerId)`, the `j`/`k` handler calls `select(next.dataset.workerId)`, and palette selection calls `select(id)` after returning to runs mode. The choice changes only how the run id is reached, not the selection, watch, or detail-loading behavior.

Selection styling is not its job. The fleet list renders `selected` and `aria-current` from the store on every render, so a re-render caused by a fleet tick already agrees with the selection and there is nothing to reapply. That is the difference from the fragment era, when a swapped-in row arrived unaware of what was selected and a separate reconciler had to walk the document and repaint it.

The fetch and the subscription are both issued because they answer different questions. The fetch fills the pane *now*; the subscription keeps it filled. Issuing only the subscription would leave the pane blank until the run next changed — which, for an idle run, could be never.

- code: groom/groom/assets/dashboard.js::select
- code: groom/groom/assets/dashboard.js::RunRow
- rule: choose the direct row, keyboard traversal, or command palette for its input context; all three select through the same run selector, and no ranking exists among them
- detail: [dashboard run select authority](dashboard-run-select-authority.md)
- refs: [dashboard selected worker state](../dashboard-selected-worker-state.md), [run watch registry](run-watch-registry.md), [dashboard client store](dashboard-client-store.md)

## Contract

- purpose: make one run the open run — recorded in the store, subscribed on the socket, and rendered in the detail pane.
- input: one workflow container id, read from the chosen row's `data-worker-id` or from the palette result's id.
- store write: sets `selected` to the id and clears `detail` to `null` in a single store write, so no render ever pairs the new selection with the previous run's pane.
- loading state: `detail: null` against a non-null `selected` is what the pane renders as `Loading…`. The two fields are written together precisely so that state cannot be mistaken for *nothing selected*.
- subscription: sends this tab's watch command for the id over the dashboard websocket, replacing whatever it was watching. A tab watches at most one run — the pane shows one — and a refused send is not retried, because the next selection or reconnect re-sends it anyway.
- detail fetch: requests [GET /worker/{container_id}](../http/groom.md#get-run-detail) and stores the parsed body as the pane's detail.
- consistency: detail — a response for a superseded selection must not replace the current selection's detail.
- verify: unchanged(subject="dashboard detail for the current selection")
- consistency: detail — a fetched response must not overwrite a frame received after that fetch began.
- verify: unchanged(subject="dashboard detail after a newer pushed detail")
- consistency: detail — a frame arriving after a fetch begins is treated as fresher than the eventual fetch response.
- verify: unchanged(subject="dashboard detail after a newer pushed detail")
- fetch failure: a rejected fetch is swallowed. The pane stays in its loading state and is filled by the watch subscription's next push, so a transient failure costs a tick rather than an error message.
- selection styling: rendered, not applied. The fleet row component receives whether it is selected and emits the `selected` class and `aria-current="true"` from that; no code walks the document toggling classes.
- accessibility effect: the open row carries `aria-current="true"` and every other row carries no `aria-current` attribute at all — absent rather than `"false"`, so assistive technology announces exactly one current row.
- focus: selection does not move focus. Clicking a row leaves focus on the row, and keyboard row movement is what moves it; the detail pane is not focused on the operator's behalf.
- stale ids: an id no longer in the fleet is written to the store like any other. The fetch returns a not-found detail body, which the pane renders as `Run not found.` — the selection is not silently cleared, because clearing it would hide why the pane went empty.
- server effect: none beyond the watch subscription. Selecting a run mutates no workflow record, no gate, and no sidecar session.

## Methods

### method-select

- sig: `async select(id: str) -> void`
- abstract: false
- does: leaves the pane in its loading state until the subscription fills it.
- verify: unchanged(subject="dashboard detail after a rejected detail fetch")
- raises: none intentionally.
- verify: unchanged(subject="dashboard detail after a rejected detail fetch")
- raises: a rejected detail fetch is caught.
- verify: unchanged(subject="dashboard detail after a rejected detail fetch")
- code: groom/groom/assets/dashboard.js::select
- detail: [dashboard run selection](dashboard-run-selection.md)
- input: the workflow container id to open.
- output: none; the effects are the store write, the watch command, and at most one detail store write.
- calls: the watch sender, then `GET /worker/{container_id}`.
- algorithm:
  1. Take the next selection sequence number.
  2. Write `selected` and a null `detail` to the store in one update.
  3. Send this tab's watch subscription for the id.
  4. Await the run detail response and parse it.
  5. Store it only if this is still the newest selection and no pushed detail has already filled the pane.
  6. Swallow a rejected fetch and leave the pane for the subscription to fill.
