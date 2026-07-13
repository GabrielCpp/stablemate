---
type: format
slug: dashboard-selected-repository-state
title: Dashboard selected repository state
---
# Dashboard selected repository state

Dashboard selected repository state is the browser-local selection object written by [select repository menu option](gui/screens/groom-dashboard.md#select-repository-menu-option) after an operator chooses a [repository menu option](gui/screens/groom-dashboard.md#repository-menu-option) rendered from [repository menu data](repository-menu-data.md). It carries the selected workflow container id, volume-relative checkout directory, and display label read by the [dashboard active pane loader](concepts/dashboard-active-pane-loader.md), Files pane, file opener, and Diff pane to request [workspace file list data](workspace-file-list-data.md), [workspace file content data](workspace-file-content-data.md), and [workspace diff data](workspace-diff-data.md) without changing the dashboard route or server-side workflow state.

- file: not an on-disk artifact; this is a browser-local JavaScript object retained for the lifetime of the loaded dashboard page.
- code: groom/groom/templates/dashboard.html::sel

## Contract

- producer: [select repository menu option](gui/screens/groom-dashboard.md#select-repository-menu-option) creates the selected value from one clicked repository-menu option's `data-container`, `data-repo`, and `data-label` attributes.
- consumers: the [dashboard active pane loader](concepts/dashboard-active-pane-loader.md) dispatches after every selection; the active Files pane loader reads `container` and `repo` to request the selected checkout's file tree; the file-row opener reads them again with a selected path to request file content; the active Diff pane loader reads them to request the selected checkout's working-tree diff; both repository picker labels read `label` for visible selection text.
- lifetime: initialized when the dashboard script loads, retained across activity-mode switches, repository-menu open/close cycles, inbox/detail refreshes, statusbar updates, and command-palette use, and replaced wholesale by the next repository-menu option selection.
- absent state: before the first repository option selection, `container` is `null`, `repo` is `""`, and `label` is `null`; entering Files or Diff mode in this state renders the appropriate picker prompt instead of sending repository-backed HTTP requests.
- selected state: after selection, `container` and `label` are copied exactly from the option dataset, while `repo` is copied from the option dataset or normalized to `""` when missing or empty; no trimming, case normalization, existence check, or registry validation occurs in browser state.
- stale state: if the selected workflow or checkout disappears after selection, the object remains unchanged until another menu option is selected or the page unloads; later Files, file-content, or Diff requests use the stale values and surface endpoint empty/error behavior in their target panes.
- write rule: selection assigns the three fields synchronously before closing the menu and before the active-pane loader issues any Files or Diff request, so the immediate load reads the new container/repository pair.
- read rule: every read is synchronous and in-memory from the loaded dashboard page; first-party code does not serialize this object to local storage, session storage, cookies, query parameters, websocket frames, or hidden inputs.
- server effect: none directly; the state only scopes later HTTP GET requests and never mutates workflow records, sidecar sessions, gates, or websocket state.
- accessibility effect: the state is reflected only by replacing visible picker-label text and by loading pane content; it does not set focus, `aria-selected`, `aria-expanded`, `aria-current`, live-region announcements, browser history, or route state.

## Fields

### field-container

- type: `str | null`
- default: `null`
- required: false before selection; true for Files, file-content, and Diff requests after selection.
- meaning: workflow container id copied from the selected option's `data-container`; it becomes the `{container_id}` route value for later file and diff HTTP requests.
- source: [repository menu data](repository-menu-data.md#field-option-container) rendered as the selected row's `data-container` attribute, then read as `dataset.container` during pointer selection.
- normalization: copied exactly as supplied by the row dataset; no empty-string guard runs at selection time, but Files and Diff pane loaders treat falsey values as absent and render `Pick a container / repo above.` instead of requesting data.
- consumers: `loadFiles` and `loadDiff` URL-encode the value as the path segment in `GET /files/{container_id}` and `GET /diff/{container_id}`; `openFile` URL-encodes it as the path segment in `GET /file/{container_id}`.

### field-repo

- type: `str`
- default: `""`
- required: true
- meaning: volume-relative checkout directory copied from the selected option's `data-repo`; an empty string selects the workflow workspace volume root for file-list/file-content requests and the default checkout for diff requests.
- source: [repository menu data](repository-menu-data.md#field-option-repo) rendered as the selected row's `data-repo` attribute, then read as `dataset.repo` during pointer selection.
- normalization: selection applies JavaScript `repo || ""`, so missing, empty, or other falsey dataset values become the empty string; non-empty strings are preserved exactly.
- consumers: `loadFiles`, `openFile`, and `loadDiff` URL-encode the value as the `repo` query parameter for workspace file-list, file-content, and diff requests.
- scope: the value is repository-directory scope only; selected files, changed-file indexes, directory collapsed classes, and parsed diff cache entries are separate pane-local state and are rebuilt or reset by later loads.

### field-label

- type: `str | null`
- default: `null`
- required: false before selection; true immediately after a repository-menu option is selected.
- meaning: visible picker label copied from the selected option's `data-label`; after selection it replaces the text content of every `.repo-picker-label` span in both Files and Diff picker buttons.
- source: [repository menu data](repository-menu-data.md#field-option-label) rendered as the selected row's `data-label` attribute, then read as `dataset.label` during pointer selection.
- normalization: copied exactly as supplied by the row dataset; if missing, the browser assigns `undefined` as text content, so correctness depends on rendered repository options carrying `data-label`.
- consumers: both native repository picker buttons expose this value as their visible label and accessible button name after selection; the search field and option filtering do not read this stored `label` value after selection.
