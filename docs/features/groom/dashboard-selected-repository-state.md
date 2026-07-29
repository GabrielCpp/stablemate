---
type: format
slug: dashboard-selected-repository-state
title: Dashboard selected repository state
---
# Dashboard selected repository state

Dashboard selected repository state is the `repo` slice of the [dashboard client store](concepts/dashboard-client-store.md): the container/checkout pair the operator picked, plus the menu's own open-time state. It is written when a [repository menu data](repository-menu-data.md) entry is selected, and read by the files and diff panes to scope every `GET /files`, `GET /file`, and `GET /diff` request. It changes no route and no server-side state.

Selection and menu contents live in one slice rather than two because they are read together on every render of the picker — the menu needs the entry list *and* the active index, and the picker button needs the label. Splitting them would mean two subscriptions to keep in step for a component that is one dropdown.

- file: not an on-disk artifact; this is a slice of the browser-local store, retained for the lifetime of the loaded dashboard page.
- code: groom/groom/assets/dashboard.js::selectRepo
- code: groom/groom/assets/dashboard.js::openRepoMenu
- code: groom/groom/assets/dashboard.js::repoItems
- refs: [dashboard client store](concepts/dashboard-client-store.md), [repository menu data](repository-menu-data.md), [workspace file list data](workspace-file-list-data.md), [workspace file content data](workspace-file-content-data.md), [workspace diff data](workspace-diff-data.md)

## Contract

- producer — selection: `selectRepo` copies `container`, `repo`, and `label` off one chosen [repository menu data](repository-menu-data.md) entry into `container`, `dir`, and `label`.
- producer — menu lifecycle: `openRepoMenu` resets `loading`, `groups`, `query`, and `active` before fetching `/repos`, and writes the fetched groups back when the response lands.
- consumers: the files pane reads `container` and `dir` to request the file tree; the file opener reads them again with a selected path to request file content; the diff pane reads them to request the working-tree diff; the picker buttons read `label`; the menu component reads `groups`, `query`, and `active`.
- lifetime: initialized when the dashboard module loads, retained across mode switches, fleet ticks, resyncs, connection-state changes, and command-palette use; the selection fields are replaced only by another selection.
- absent state: before the first selection, `container` is `null`, `dir` is `""`, and `label` is `null`. Files and diff mode render `Pick a container / repo above.` in that state and send no repository-scoped request.
- selected state: `container` and `label` are copied exactly from the entry; `dir` is the entry's `repo` or `""`. No trimming, case normalization, existence check, or registry validation happens in the browser.
- stale state: if the selected workflow or checkout disappears after selection, the slice is unchanged until another entry is picked. Later requests use the stale pair and surface the panes' own empty or failure states rather than clearing the selection.
- write ordering: selection assigns the three fields, updates the picker labels, and dispatches the active-pane load synchronously, before the menu closes — so the load already sees the new pair.
- menu freshness: `groups` is discarded and re-fetched every time the menu opens rather than cached, because checkout discovery is a per-container process and a cached list would show checkouts that no longer exist without any signal that it was stale.
- not persisted: the slice is never serialized to local storage, session storage, cookies, query parameters, the URL, hidden inputs, or any websocket frame. A reload starts with nothing selected.
- not pushed: no server message writes this slice. The socket carries fleet state; the selection is the tab's own.
- server effect: none. It only scopes later HTTP GETs, and mutates no workflow record, sidecar session, gate, or socket state.
- accessibility effect: selection replaces visible picker-label text and loads pane content. The menu's `active` index is separately published to the combobox as `aria-activedescendant` by the menu component, which is the one place that knows which entry ended up at which index after filtering.

## Fields

### field-container

- type: `str | null`
- default: `null`
- required: false before selection; required by every repository-scoped request after it.
- meaning: the workflow container id from the selected entry; it becomes the `{container_id}` route segment of the files, file-content, and diff requests.
- source: [repository menu data](repository-menu-data.md#field-group-container).
- normalization: copied exactly. No empty-string guard runs at selection time; the panes treat a falsey value as *nothing selected* and render the picker prompt instead of requesting data.

### field-dir

- type: `str`
- default: `""`
- required: true
- meaning: the volume-relative checkout directory, sent as the `repo` query parameter. `""` selects the workspace root for file requests and the first discovered checkout for diff requests.
- source: [repository menu data](repository-menu-data.md#field-entry-repo).
- normalization: `item.repo || ""`, so a missing or falsey entry value becomes the empty string; a non-empty string is preserved exactly.
- name: the store calls it `dir` rather than `repo` because the enclosing slice is already `repo`; the wire name on every request remains `repo`.
- scope: repository-directory scope only. The selected file path, the changed-file index, collapsed directory state, and the parsed diff cache are separate pane-local state, rebuilt or reset by the load that selection triggers.

### field-label

- type: `str | null`
- default: `null`
- required: false before selection.
- meaning: the visible picker text; after selection it replaces the text of every `.repo-picker-label` in the files and diff picker buttons, which is also those buttons' accessible name.
- source: [repository menu data](repository-menu-data.md#field-entry-label).
- normalization: copied exactly. It is composed server-side, so the client never joins a container name and a checkout path itself.

### field-loading

- type: `bool`
- default: `false`
- required: true
- meaning: whether the `/repos` fetch is in flight. The menu renders `Loading…` for `true` and `No repositories available.` for `false` with no entries — two states, so an empty fleet never reads as a slow one.

### field-groups

- type: `list` of [repository menu data](repository-menu-data.md#field-groups) group objects
- default: `[]`
- required: true
- meaning: the menu's contents as fetched, held in the server's grouping and order.
- normalization: a rejected fetch and a missing body both become `[]`, which renders the same empty state as a genuinely empty fleet. The menu has no error state of its own.

### field-query

- type: `str`
- default: `""`
- required: true
- meaning: the picker's search text. Filtering is client-side and case-insensitive over each entry's `label`; it never re-requests `/repos`, because the whole menu is already in the tab.
- reset: cleared every time the menu opens.

### field-active

- type: `int`
- default: `0`
- required: true
- meaning: the keyboard-highlighted row's index **into the filtered entry list**, not into `groups`. It is clamped to the filtered list's bounds at render time, so narrowing the query can never leave the pointer past the end.
- reset: set to `0` on menu open and on every fetch resolution.

## Algorithms

### algorithm-select-a-checkout

- step: Opening the picker clears the slice's menu fields, marks it loading, and fetches [repository menu data](repository-menu-data.md).
- step: The menu component flattens `groups` into rows, applies `query`, and clamps `active` to the result.
- step: Choosing a row writes `container`, `dir`, and `label`, updates both picker buttons' visible text, and calls the active-pane loader.
- step: The loader requests the files tree or the working-tree diff for the new pair, depending on the current mode; every other mode is a no-op.
- step: The menu closes, returning focus to the button that opened it.
