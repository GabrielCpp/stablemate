---
type: concept
slug: dashboard-active-pane-loader
title: dashboard active pane loader
---
# dashboard active pane loader

Dashboard active pane loader is the browser-side dispatch layer used by [select repository menu option](../gui/screens/groom-dashboard.md#select-repository-menu-option) after [dashboard selected repository state](../dashboard-selected-repository-state.md) is written. It reads the current dashboard activity mode and reloads only the pane whose data depends on the selected repository: Files uses [workspace file list data](../workspace-file-list-data.md), Diff uses [workspace diff data](../workspace-diff-data.md), and every other mode is a no-op. It is the boundary between repository-menu selection and the Files/Diff pane reload behavior documented on the [groom dashboard](../gui/screens/groom-dashboard.md).

- code: groom/groom/templates/dashboard.html::loadActivePane

## Contract

- purpose: route a newly selected repository to the data loader for the currently active repository-dependent pane.
- caller contract: [select repository menu option](../gui/screens/groom-dashboard.md#select-repository-menu-option) calls this loader synchronously after copying the option's selected container, repository path, and label into [dashboard selected repository state](../dashboard-selected-repository-state.md) and after updating every `.repo-picker-label` text node, but before the repository menu is closed.
- input: no function parameters; reads the dashboard shell's current activity mode from the root `.app` element and relies on delegated pane loaders to read selected repository state.
- output: no return value; completion means either one pane loader has been invoked or no repository-backed pane matched.
- mode source: the root `.app` element's `data-mode` attribute as stored in `document.querySelector(".app").dataset.mode` at the moment of dispatch.
- files branch: when `data-mode` is exactly `files`, invokes the Files pane load path for the current selected repository. That path reads `sel.container` and `sel.repo`, renders `Pick a container / repo above.` if no container exists, otherwise sets `#files-tree` to `Loading files...`, resets `#file-view` to `Select a file to view it.`, requests [GET /files/{container_id}](../http/groom.md#get-workspace-file-list), normalizes the newline response into path strings, and renders [workspace file list data](../workspace-file-list-data.md) as a file tree, `(no files)`, or `failed to load`.
- diff branch: when `data-mode` is exactly `diff`, invokes the Diff pane load path for the current selected repository. That path reads `sel.container` and `sel.repo`, renders `Pick a container / repo above.` if no container exists, otherwise sets `#diff-tree` to `Loading changes...`, resets `#diff-view` to `Select a changed file to see its diff.`, requests [GET /diff/{container_id}](../http/groom.md#get-workspace-diff), parses non-empty [workspace diff data](../workspace-diff-data.md) into changed-file records, stores them on the diff tree, and renders the changed-file tree, `(no changes)`, or `failed to load`.
- no-op branch: when `data-mode` is `inbox`, `settings`, missing, or any other value, sends no HTTP request and leaves the selected repository state and picker labels as the only repository-selection changes.
- ordering: reads the activity mode once per repository selection and dispatches immediately; it does not debounce, queue, retry, cancel an in-flight prior pane request, or re-read the mode after asynchronous work begins in a delegated loader.
- equality rule: mode comparison is exact string equality against `files` and `diff`; no trimming, case folding, fallback default, or validation of unknown modes is performed.
- error behavior: the dispatch layer intentionally catches no errors and surfaces no pane-level failure text itself; fetch or parse failures are handled by the delegated pane loaders.
- state mutation: does not itself write selected repository state, picker labels, activity mode, selected worker state, file tree HTML, diff tree HTML, parsed diff cache, websocket state, server workflow state, browser history, or the browser URL; all visible pane updates belong to the delegated Files or Diff loader.

## Methods

### method-load-active-pane

- sig: `loadActivePane() -> void`
- abstract: false
- raises: none intentionally raised by the dispatch layer.
- code: groom/groom/templates/dashboard.html::loadActivePane
- input: none; reads `.app.dataset.mode` from the loaded dashboard DOM.
- output: none; side effects are limited to invoking zero or one delegated pane loader.
- calls: `loadFiles()` only for `files` mode; `loadDiff()` only for `diff` mode; no call for inbox, settings, missing, or unknown mode values.

Reads the dashboard mode once, compares it with the repository-backed pane names, and calls exactly one pane loader for `files` or `diff`. It does not fall through, retry, queue work, or normalize the mode string before the comparison.

#### Algorithm

1. Select the root `.app` element from the dashboard shell.
2. Read its `data-mode` dataset value into a local mode value.
3. If the mode value is exactly `files`, invoke the Files pane loader and stop.
4. Otherwise, if the mode value is exactly `diff`, invoke the Diff pane loader and stop.
5. Otherwise, return without invoking a pane loader.

#### Effects

- Reads: `.app[data-mode]` from the loaded dashboard shell.
- Calls: the Files pane loader when the mode is `files`; that handler is already grounded by [select activity files mode](../gui/screens/groom-dashboard.md#select-activity-files-mode) and consumes [workspace file list data](../workspace-file-list-data.md).
- Calls: the Diff pane loader when the mode is `diff`; that handler is already grounded by [select activity diff mode](../gui/screens/groom-dashboard.md#select-activity-diff-mode) and consumes [workspace diff data](../workspace-diff-data.md).
- Skips: every pane loader when the mode is not `files` or `diff`.
- Delegates: selected container and repository reads to the pane loaders, which consume [dashboard selected repository state](../dashboard-selected-repository-state.md) after the repository option handler has written it.
- Does not mutate: activity mode, selected worker id, selected repository state, picker labels, inbox rows, worker detail, command palette state, websocket connection, browser URL, or server-side workflow state.
