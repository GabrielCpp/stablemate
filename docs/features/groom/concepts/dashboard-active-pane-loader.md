---
type: concept
slug: dashboard-active-pane-loader
title: Dashboard active pane loader
---
# Dashboard active pane loader

Dashboard active pane loader is the browser-side dispatch layer that reloads whichever pane depends on the selected checkout. It is called after [dashboard selected repository state](../dashboard-selected-repository-state.md) is written by a repository-menu selection, and it reads the store's current mode to decide what — if anything — to request: `files` reloads [workspace file list data](../workspace-file-list-data.md), `diff` reloads [workspace diff data](../workspace-diff-data.md), and every other mode is a no-op. It is the boundary between picking a checkout and the Files/Changes pane reload behaviour documented on the [groom dashboard](../gui/screens/groom-dashboard.md).

It exists because the picker is shared. One repository menu serves both repository-backed panes, so the selection handler cannot name the loader it wants — it has to ask what is open. The mirror-image case, switching mode with a checkout already selected, is handled by the mode setter, which calls the same two loaders directly; this dispatcher is the selection-changed half of that pair.

- code: groom/groom/assets/dashboard.js::loadActivePane
- refs: [dashboard client store](dashboard-client-store.md), [dashboard selected repository state](../dashboard-selected-repository-state.md), [workspace file list data](../workspace-file-list-data.md), [workspace diff data](../workspace-diff-data.md)

## Contract

- purpose: route a newly selected checkout to the data loader for the currently active repository-backed pane.
- caller contract: the repository-menu selection handler calls this loader synchronously, after copying the chosen entry's container, checkout directory, and label into [dashboard selected repository state](../dashboard-selected-repository-state.md) and after updating every picker label, and before the menu closes. The loader therefore always sees the new pair, never the previous one.
- input: no parameters. The mode is read from the [dashboard client store](dashboard-client-store.md), and the delegated loaders read the selected pair from the same store.
- mode source: the store's `mode` value, which is the same value the mode buttons write. It is store state rather than a DOM attribute read, so a mode change and a selection change cannot disagree about what is open.
- output: no return value; completion means either one pane loader has been invoked or no repository-backed pane matched.
- files branch: mode exactly `files` invokes the Files pane loader, which resets the pane to its loading state, requests [GET /files/{container_id}](../http/groom.md#serve-workspace-file-list) for the selected pair, and stores the parsed path list.
- diff branch: mode exactly `diff` invokes the Changes pane loader, which resets the pane to its loading state, requests [GET /diff/{container_id}](../http/groom.md#serve-working-tree-diff) for the selected pair, parses non-empty diff text into changed-file records, and stores them.
- no-op branch: `runs`, `telemetry`, `settings`, and any other value send no request. Those panes do not read the selected checkout, so reloading them on a selection would be work no operator asked for.
- unselected guard: neither delegated loader requests anything when no container is selected; the dispatcher does not check that itself, because the guard belongs with the loader that would otherwise build a URL from a null id.
- ordering: the mode is read once per call and dispatched immediately. There is no debounce, queue, retry, or cancellation of a prior in-flight pane request; a superseded response is discarded by the pane's own state write rather than by this layer.
- equality rule: exact string equality against `files` and `diff`. No trimming, case folding, fallback default, or validation of unknown modes.
- error behavior: this layer catches nothing and renders nothing. Fetch and parse failures become the delegated loader's error state, which the pane renders as `failed to load`.
- state mutation: it writes no store slice itself — not the selection, not the mode, not the pane data. Every visible change belongs to the loader it delegates to.

## Methods

### method-load-active-pane

- sig: `loadActivePane() -> void`
- abstract: false
- raises: none intentionally.
- code: groom/groom/assets/dashboard.js::loadActivePane
- input: none; reads the store's `mode`.
- output: none; the side effect is invoking zero or one delegated pane loader.
- calls: the Files pane loader for `files`, the Changes pane loader for `diff`, nothing otherwise.
- algorithm:
  1. Read `mode` from the store.
  2. If it is exactly `files`, invoke the Files pane loader and stop.
  3. Otherwise, if it is exactly `diff`, invoke the Changes pane loader and stop.
  4. Otherwise, return without invoking a loader.
