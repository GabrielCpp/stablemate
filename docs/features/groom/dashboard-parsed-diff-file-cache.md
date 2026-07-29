---
type: format
slug: dashboard-parsed-diff-file-cache
title: Dashboard parsed diff file cache
---
# Dashboard parsed diff file cache

Dashboard parsed diff file cache is the parsed changed-file array the Diff pane
holds in the [dashboard client store](concepts/dashboard-client-store.md) as the
`diff` slice's `files` member. It is created once per Diff pane load, when
[workspace diff data](workspace-diff-data.md) comes back with non-whitespace unified
diff text and the third-party diff2html parser turns it into file entries. It feeds
the [dashboard tree builder](concepts/dashboard-tree-builder.md) — which is what puts
[diff file row](gui/screens/groom-dashboard.md#diff-file-row) entries on the page —
and it is what makes [select diff file row](gui/screens/groom-dashboard.md#select-diff-file-row)
free: the whole diff was parsed when the pane loaded, so choosing a file renders one
already-parsed entry rather than issuing another request.

It used to live on the DOM, assigned as a `_files` property on the `#diff-tree`
element and read back out by a click handler through a `data-file-idx` attribute.
Both of those are gone. The array is store state now and the selected index is store
state beside it, which removes the whole class of bug where a stale property outlived
the rows that indexed into it — there is no longer a way for the rows on screen and
the array they address to come from different loads, because one render derives both.

- file: not an on-disk artifact; this is a transient in-memory slice of one tab's client store.
- code: groom/groom/assets/dashboard.js::loadDiff
- code: groom/groom/assets/dashboard.js::DiffTree
- code: groom/groom/assets/dashboard.js::DiffView
- refs: [workspace diff data](workspace-diff-data.md), [dashboard path tree](dashboard-path-tree.md)

## Contract

- producer: the Diff pane loader, after `GET /diff/{container_id}?repo={repo}` returns JSON whose `diff` member holds non-whitespace text and diff2html is present to parse it.
- parser input: the loader hands the raw diff text to the parser exactly as the endpoint returned it. It does not pre-split, filter, normalize paths, redact content, or inspect the HTTP status of a fulfilled response.
- storage: the parsed array is written to the client store's `diff` slice as `files`, alongside the selected index `idx` and a `status`. It is not serialized into markup, browser storage, URL state, server state, or any websocket frame.
- consumer: the Diff tree island maps each entry to a `{path, idx, add, del}` builder entry and renders the resulting [dashboard path tree](dashboard-path-tree.md); the viewer island reads `files[idx]` and passes that one entry to diff2html's renderer.
- scope: one tab, one loaded pane, one container/repository selection. Loading the pane again — for the same repository or another — replaces the slice wholesale.
- absent states: an empty array is stored, rather than the slice left untouched, for whitespace-only diff text and for a parse that yields no files. The two are indistinguishable by design and both render `(no changes)`. A rejected fetch or unparseable body sets `status: "error"` with an empty array.
- reset rule: every load begins by writing `{status: "loading", files: [], idx: -1}`, so a failed or empty reload cannot leave the previous load's entries addressable. This is what the DOM-property version could not guarantee.
- selection invariant: `idx` is a position in the array stored in the same slice, and both are written by the same store update. There is no path by which a row's index and the array it indexes come from different loads, and no bounds check is needed beyond the viewer's `files[idx]` returning undefined for the initial `-1`.
- ordering: array positions are parser order and are never reordered. The visible tree sorts a copy per level, so a row's position on screen says nothing about its index.
- third-party boundary: each entry is an opaque diff2html payload for final rendering. First-party code reads only `newName`, `oldName`, `addedLines` and `deletedLines`, and retains the whole object for the viewer.
- escaping: diff2html escapes what it emits, which is why the raw diff crosses the wire unsplit rather than having half a parser reimplemented server-side. Nothing in this cache is interpolated into markup by first-party code.

## Fields

### field-files

- type: `Array<Diff2HtmlParsedFile>`
- default: `[]`
- required: true
- wire-key: `files`, within the store's `diff` slice
- meaning: the ordered parsed changed-file entries for the currently loaded repository diff.
- write rule: written exactly twice per load — emptied when the load starts, replaced when it settles.

### field-idx

- type: `int`
- default: `-1`
- required: true
- wire-key: `idx`, within the store's `diff` slice
- meaning: the position in `files` of the changed file whose diff the viewer is showing. `-1` means none, which renders the viewer's prompt.
- source: written by the diff-file row's click handler, which closes over the index rather than reading it back off a data attribute.

### field-new-name

- type: `str | null`
- default: parser supplied
- required: false
- meaning: the changed file's path after the diff. The tree uses it as the grouping and display path unless it is missing or `/dev/null`.

### field-old-name

- type: `str | null`
- default: parser supplied
- required: false
- meaning: the changed file's path before the diff. Used as the grouping and display path when `newName` is missing or `/dev/null` — the deleted-file case.

### field-added-lines

- type: `int`
- default: parser supplied
- required: true for rendered rows
- meaning: the added-line count, carried onto the builder entry as `add` and shown in the row as `+N`.

### field-deleted-lines

- type: `int`
- default: parser supplied
- required: true for rendered rows
- meaning: the deleted-line count, carried onto the builder entry as `del` and shown in the row as `-N`.

### field-render-payload

- type: `Diff2HtmlParsedFile`
- default: parser supplied
- required: true to render a selected row
- meaning: the complete parsed entry, passed as the single element of an array to diff2html's HTML renderer.
- render options: `drawFileList: false`, `matching: "lines"`, `outputFormat: "line-by-line"`, `colorScheme: "dark"`.
