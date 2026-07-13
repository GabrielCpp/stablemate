---
type: format
slug: dashboard-diff-file-tree
title: Dashboard diff file tree
---
# Dashboard diff file tree

Dashboard diff file tree is the browser-local recursive data shape produced by [dashboard diff file tree builder](concepts/dashboard-diff-file-tree-builder.md) from the [dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md). It feeds the [groom dashboard](gui/screens/groom-dashboard.md) Diff pane renderer, which turns directory nodes into [diff directory toggle](gui/screens/groom-dashboard.md#diff-directory-toggle) components and changed-file leaves into [diff file row](gui/screens/groom-dashboard.md#diff-file-row) components.

- file: not an on-disk artifact; this is an in-memory browser object built for one Diff pane render.
- code: groom/groom/templates/dashboard.html::buildFileTree

## Contract

- producer: [dashboard diff file tree builder](concepts/dashboard-diff-file-tree-builder.md).
- consumer: Diff pane renderer grounded by [diff directory toggle](gui/screens/groom-dashboard.md#diff-directory-toggle) and [diff file row](gui/screens/groom-dashboard.md#diff-file-row).
- lifetime: one tree is created for each non-empty successful Diff pane load after Diff2Html parsing returns at least one file entry, and is discarded after the renderer returns its HTML string.
- scope: represents only the selected container/repository working-tree diff for the current Diff pane load.
- root: always a node with the same shape as every directory node; root has no visible name and is not itself rendered as a directory row.
- path source: each leaf is grouped by the parsed entry's `newName` when that value is truthy and not `/dev/null`; otherwise it is grouped by `oldName`.
- path parsing: the selected path is coerced with JavaScript `String(...)` and split only on literal `/`; path segments are not normalized, decoded, trimmed, collapsed, or rejected.
- empty-state: the Diff pane loader does not build this shape when no repository is selected, the diff response is whitespace-only, parsing returns zero file entries, or the request fails.
- ordering: the shape preserves parser insertion order and original parsed-file indexes; visible directory and file ordering is imposed later by the renderer.
- consumer mutation: rendering walks directory keys in sorted order without replacing the `dirs` maps, but sorts every consumed node's `files` array in place by displayed `name` before emitting rows; `idx` remains the stable link back to the parsed diff cache.
- duplicate handling: duplicate selected paths produce separate file leaves under the same terminal node; no merge, overwrite, or de-duplication is performed.

## Fields

### field-root

- type: `{ dirs: Record<string, DashboardDiffFileTreeNode>, files: DashboardDiffFileTreeFile[] }`
- default: `{ dirs: {}, files: [] }`
- required: true
- meaning: invisible root node returned by the builder and passed to the renderer; its `dirs` entries become top-level rendered directories and its `files` entries become top-level rendered changed-file rows.

### field-node-dirs

- type: `Record<string, DashboardDiffFileTreeNode>`
- default: `{}`
- required: true
- meaning: child directory map for a root or directory node, keyed by the exact directory segment string derived from the selected parsed diff file path.
- key rule: every segment before the final slash-delimited segment is used as a directory key under the current node; repeated slashes or leading slashes can therefore create empty-string directory keys.
- merge rule: when another changed file reaches the same key under the same parent, it reuses the existing child node.

### field-node-files

- type: `DashboardDiffFileTreeFile[]`
- default: `[]`
- required: true
- meaning: changed-file leaves directly under this root or directory node; changed files nested below child directories live in the child node's own `files` collection.
- insertion order: leaves are appended in parsed-cache array order for the terminal node reached by their path; the renderer may later sort this array in place by `name`.

### field-file-name

- type: `str`
- default: none
- required: true
- meaning: final slash-delimited segment of the selected changed-file path; rendered as the visible file basename in the generated diff row.
- source rule: a path with no slash produces a root-level leaf whose `name` is the whole coerced selected path; a trailing slash produces an empty-string `name` leaf under the preceding directory path.

### field-file-index

- type: `int`
- default: none
- required: true
- meaning: original zero-based index of the parsed file entry in the [dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md); retained on the generated row as `data-file-idx` so row selection can recover the full parsed file object after visual sorting.

### field-added-lines

- type: `int`
- default: parser supplied
- required: true for rendered diff-file rows.
- meaning: added-line count copied from the parsed file entry and rendered in the generated row as `+{addedLines}`.
- source field: copied from the parsed diff entry's `addedLines` member without numeric coercion or fallback by first-party code.

### field-deleted-lines

- type: `int`
- default: parser supplied
- required: true for rendered diff-file rows.
- meaning: deleted-line count copied from the parsed file entry and rendered in the generated row as `-{deletedLines}`.
- source field: copied from the parsed diff entry's `deletedLines` member without numeric coercion or fallback by first-party code.
