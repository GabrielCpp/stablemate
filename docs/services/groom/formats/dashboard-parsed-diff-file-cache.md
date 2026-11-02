---
type: format
slug: dashboard-parsed-diff-file-cache
title: Dashboard parsed diff file cache
---
# Dashboard parsed diff file cache

Dashboard parsed diff file cache is the parsed changed-file array the run Diff tab
holds in the [dashboard client store](../concepts/dashboard-client-store.md) as the
`runDiff` slice's `files` member. It is created once per diff read, when
[workspace diff data](workspace-diff-data.md) comes back with non-whitespace unified
diff text and the third-party diff2html parser turns it into file entries. It feeds
the [dashboard tree builder](../concepts/dashboard-tree-builder.md), which is what puts
[diff file row](../gui/screens/groom-dashboard.md#detail-diff-file-row) entries on the page,
and it is what makes choosing a file free: the whole diff was parsed when the tab
loaded, so choosing a file renders one already-parsed entry rather than issuing
another request.

The array is store state and the chosen file is store state beside it, which removes
the whole class of bug where a stale property outlived the rows that indexed into
it. The rows on screen and the array they address always come from one render of
one read.

- file: not an on-disk artifact; this is a transient in-memory slice of one tab's client store.
- code: groom/groom/assets/dashboard.js::loadRunDiff@a79bfdf4c0b1
- code: groom/groom/assets/dashboard.js::DiffTab@ed8babf5c628
- code: groom/groom/assets/dashboard.js::RunFileDiff@139e9580d270
- detail: [dashboard diff representation selection](../concepts/dashboard-diff-representation-selection.md)
- refs: [workspace diff data](workspace-diff-data.md), [dashboard path tree](dashboard-path-tree.md)

## Contract

The diff read starts with `GET /diff/{container_id}?repo={repo}`, with `&view=branch` while the run's switch is on Since branch start, and decodes a
fulfilled response as JSON before considering its `diff` member.

- parser input: the loader hands the raw diff text to the parser exactly as the endpoint returned it. It does not pre-split, filter, normalize paths, redact content, or inspect the HTTP status of a fulfilled response beyond requiring success.
- storage: the parsed array is written to the client store's `runDiff` slice as `files`, alongside the chosen file's `path` and a `status`. It is not serialized into markup, browser storage, URL state, server state, or any websocket frame.
- consumer: the Diff tab maps each entry to a `{path, idx, add, del}` builder entry and renders the resulting [dashboard path tree](dashboard-path-tree.md); the viewer reads the entry for the chosen path and passes `files[idx]` to diff2html's renderer.
- scope: one run, one checkout, one view. Reading again, for the same checkout and view or another, replaces the slice wholesale, and a refresh of the same checkout keeps the chosen path.
- absent states: an empty array is stored, rather than the slice left untouched, for whitespace-only diff text and for a parse that yields no files. A failed body, a rejected fetch or a parser that cannot read the text sets `status: "failed"` with an empty array, and the tab shows that as unreadable instead of as no changes.
- reset rule: a read of another run, another checkout or the other view begins by writing a loading slice with no files and no chosen path, so a failed or empty reload cannot leave the previous read's entries addressable.
- selection invariant: `idx` on a builder entry is a position in the array stored in the same slice, and both are written by the same store update. A chosen path that is absent from the new read falls back to the first changed file.
- consistency: field-files — array positions in `files` are parser order and are never reordered — each diff-tree entry's `idx` is fixed to its position at build time, not recomputed after the [dashboard tree builder](../concepts/dashboard-tree-builder.md) sorts a copy of the entries per level for display, so a row's position on screen says nothing about its index into `files`.
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

### field-path

- type: `str | null`
- default: `null`
- required: true
- wire-key: `path`, within the store's `runDiff` slice
- meaning: the path of the changed file whose diff the viewer is showing. `null`, or a path the latest read does not contain, shows the first changed file.
- source: written by the diff-file row's click handler, and kept across a refresh of the same checkout.

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
