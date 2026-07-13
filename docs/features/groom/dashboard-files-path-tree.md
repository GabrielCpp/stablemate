---
type: format
slug: dashboard-files-path-tree
title: Dashboard files path tree
---
# Dashboard files path tree

Dashboard files path tree is the browser-local recursive data shape produced by [dashboard files path tree builder](concepts/dashboard-files-path-tree-builder.md) from [workspace file list data](workspace-file-list-data.md). It feeds the [groom dashboard](gui/screens/groom-dashboard.md) Files pane renderer, which turns directory nodes into [files directory toggle](gui/screens/groom-dashboard.md#files-directory-toggle) components and file leaves into [files file row](gui/screens/groom-dashboard.md#files-file-row) components.

- file: not an on-disk artifact; this is an in-memory browser object built for one Files pane render.
- code: groom/groom/templates/dashboard.html::buildPathTree

## Contract

- producer: [dashboard files path tree builder](concepts/dashboard-files-path-tree-builder.md).
- consumer: Files pane renderer grounded by [files directory toggle](gui/screens/groom-dashboard.md#files-directory-toggle) and [files file row](gui/screens/groom-dashboard.md#files-file-row).
- lifetime: one tree is created for each non-empty successful Files pane load and is discarded after the renderer returns its HTML string.
- scope: represents only the selected container/repository file list for the current Files pane load.
- root: always a node with the same shape as every directory node; root has no visible name and is not itself rendered as a directory row.
- node invariant: every root or directory node has both `dirs` and `files`; no node carries its own name, parent pointer, full path, open/collapsed state, selection state, or rendered HTML.
- file invariant: every file leaf has `name` and `path`; it has no child collections, selected state, rendered label, file content, or endpoint response metadata.
- path segmentation: each normalized source path is split on literal `/`; every segment before the final segment is treated as a directory key and the final segment is treated as the file leaf name.
- directory reuse: when two paths share the same directory segment under the same parent, both paths reuse the same node object for that segment.
- duplicate rule: duplicate source paths are not deduplicated; each occurrence appends another file leaf with the same `name` and `path` to the terminal node's `files` array.
- validation: the shape assumes the Files pane loader already trimmed lines and removed blanks; the builder does not reject repeated slashes, dot segments, traversal-looking text, duplicate names, or an empty final segment if such a path reaches it.
- escaping: raw segment and path strings are retained; HTML escaping happens later when the renderer turns directory and file leaves into DOM strings.
- empty-state: the Files pane loader does not build this shape when the normalized path list is empty; it renders `(no files)` instead.
- ordering: the shape preserves insertion order from the normalized path list inside each `files` array and in directory-map insertion order; visible directory and file ordering is imposed later by the renderer.
- consumer mutation: rendering walks directory keys in sorted order without replacing `dirs`, but sorts every consumed node's `files` array in place by file `name` before emitting file rows.

## Fields

### field-root

- type: `{ dirs: Record<string, DashboardFilesPathTreeNode>, files: DashboardFilesPathTreeFile[] }`
- default: `{ dirs: {}, files: [] }`
- required: true
- meaning: invisible root node returned by the builder and passed to the renderer; its `dirs` entries become top-level rendered directories and its `files` entries become top-level rendered file rows.
- population: starts empty for each build; every input path either creates or reuses child directory nodes below this object before appending one file leaf.
- visibility: never rendered as a row and never receives collapsed or selected UI state.
- empty-build rule: when called with an empty input array, the builder returns this initialized root with no child directories and no file leaves; the normal Files pane load path avoids that call and renders `(no files)` instead.

### field-node-dirs

- type: `Record<string, DashboardFilesPathTreeNode>`
- default: `{}`
- required: true
- meaning: child directory map for a root or directory node, keyed by the exact directory segment string from the input path.
- key contract: keys are literal path segments as produced by splitting on `/`; they are not normalized, escaped, sorted, or joined with ancestor names inside this shape.
- value contract: each value is another node with its own required `dirs` and `files` members.
- reuse rule: assigning a path through an existing key keeps the existing child node and appends deeper content under it.
- edge-case rule: leading slashes, repeated slashes, and directory-position trailing slash segments can create empty-string directory keys if such paths reach the builder.

### field-node-files

- type: `DashboardFilesPathTreeFile[]`
- default: `[]`
- required: true
- meaning: file leaves directly under this root or directory node; files nested below child directories live in the child node's own `files` collection.
- item contract: each item is a file leaf object with required `name` and `path` fields.
- ordering: insertion order follows the order in which matching terminal paths are encountered; sibling file display sorting is not stored here.
- consumer mutation: the renderer sorts this array in place by `name` before emitting rows, so this array may no longer reflect insertion order after rendering.
- duplicates: multiple leaves with the same `name` or `path` may appear when the source path list contains duplicates or same-basename siblings under the same terminal node.

### field-file-name

- type: `str`
- default: none
- required: true
- meaning: final slash-delimited segment of the source path; rendered as the visible file basename in the generated file row.
- source: `path.split("/")[path.split("/").length - 1]` for the source path being inserted.
- normalization: not trimmed, escaped, case-folded, or de-duplicated by the tree shape after the Files pane loader has normalized the source line list.
- edge-case rule: a path with no slash produces a root-level leaf whose `name` is the full path string; a trailing slash produces an empty-string `name` leaf under the preceding directory path.

### field-file-path

- type: `str`
- default: none
- required: true
- meaning: original full repo-relative path string from the normalized file-list response; retained on the generated row as the selected file path used for later file-content requests.
- source: the exact path string currently being inserted from [workspace file list data](workspace-file-list-data.md) after browser-side line trimming and blank-line filtering.
- use: copied to the generated file row's `data-path` attribute and later sent as the `path` query value to [GET /file/{container_id}](http/groom.md#get-workspace-file-content) when a file row is selected.
- escaping: copied into generated HTML only after HTML escaping by the renderer; the in-memory field itself remains the raw normalized path string.
