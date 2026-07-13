---
type: concept
slug: dashboard-files-path-tree-builder
title: Dashboard files path tree builder
---
# Dashboard files path tree builder

Dashboard files path tree builder is the browser-side transformation used by [select activity files mode](../gui/screens/groom-dashboard.md#select-activity-files-mode) after [workspace file list data](../workspace-file-list-data.md) has been fetched and normalized. It converts repo-relative path strings into the recursive [dashboard files path tree](../dashboard-files-path-tree.md) consumed by the generated [files directory toggle](../gui/screens/groom-dashboard.md#files-directory-toggle) and [files file row](../gui/screens/groom-dashboard.md#files-file-row) components.

- code: groom/groom/templates/dashboard.html::buildPathTree

## Contract

- purpose: group flat repo-relative file paths into directory nodes and file leaves for the Files pane renderer.
- input: `string[]` from normalized [workspace file list data](../workspace-file-list-data.md); current callers pass only non-empty arrays after splitting the HTTP text body on newlines, trimming each line, and discarding empty strings, but the builder itself also accepts an empty array and returns an empty root node.
- output: one fresh [dashboard files path tree](../dashboard-files-path-tree.md) root node with `dirs` and `files` collections.
- path interpretation: `/` separates directory segments; every segment before the final segment is a directory name under the current parent, and the final segment is the file basename under that terminal node.
- duplicate handling: identical input paths append independent file leaves to the same terminal node; no file deduplication, overwrite, or merge occurs.
- directory merging: repeated directory segments under the same parent reuse the same directory node so files sharing a directory prefix appear under one branch.
- ordering: preserves input order while building nodes; sorting belongs to the renderer that consumes the tree.
- validation: does not reject duplicate paths, paths without directory separators, repeated slashes, dot segments, traversal-looking names, or empty final segments that survived caller normalization.
- escaping: does not escape text for HTML; escaping belongs to the renderer that turns the tree into DOM strings.
- data ownership: creates a new root object and child node objects for each call; it does not retain module-level cache, attach DOM state, or mutate the caller's path strings.
- file leaf contract: every inserted source path creates exactly one file leaf with `name` equal to the final slash-delimited segment and `path` equal to the original source path string.
- failure boundary: assumes `paths` is array-like enough to provide `forEach` and each item is string-like enough to provide `split`; invalid caller inputs may raise ordinary JavaScript runtime errors before any domain-specific handling.

## Methods

### method-build-path-tree

- sig: `buildPathTree(paths: string[]) -> DashboardFilesPathTree`
- abstract: false
- raises: no domain-specific errors for ordinary normalized path strings; ordinary JavaScript runtime errors can surface if `paths` is not iterable with `forEach` or a path item does not provide `split`.
- code: groom/groom/templates/dashboard.html::buildPathTree
- input: `paths` is the normalized browser-side path array from [workspace file list data](../workspace-file-list-data.md); each item is expected to be a repo-relative path string already trimmed and blank-filtered by the Files pane loader.
- output: a fresh [dashboard files path tree](../dashboard-files-path-tree.md) root node with required `dirs` and `files` collections.
- effects: allocates only the returned in-memory tree and its file leaf objects; it does not read or write DOM, send network requests, change selected repository state, fetch file contents, sort output, escape HTML, or mutate server state.
- calls: no first-party groom symbol; the layer bottoms out in JavaScript array iteration, string splitting, object property lookup, and array append operations.
- algorithm:
  1. Initialize a root node with empty `dirs` and `files` collections.
  2. For each source path in array order, split the path on literal `/` characters.
  3. Start at the root node for the current path.
  4. For each segment before the final segment, create a child directory node for that segment when it is absent under the current node, then move the current node to that child.
  5. Append a file leaf to the current node's `files` collection with `name` set to the final split segment and `path` set to the original source path string.
  6. Return the root node after every source path has been inserted.

Builds a fresh tree for one Files pane load and returns it synchronously without reading or writing DOM state. For an empty `paths` array, returns the initialized root with no child directories and no file leaves.

#### Effects

- Creates: a root [dashboard files path tree](../dashboard-files-path-tree.md) node initialized with empty `dirs` and `files` collections.
- Iterates: each input path string in the array order supplied by the caller.
- Splits: the current path on `/` to identify directory segments and the final file segment.
- Creates: a missing directory node for each directory segment along the path, each initialized with empty `dirs` and `files` collections.
- Reuses: an existing directory node when another path already created the same segment under the same parent.
- Appends: one file leaf to the terminal node's `files` collection with `name` set to the final segment and `path` set to the original full repo-relative path string; duplicate terminal names and duplicate full paths remain separate leaves.
- Leaves unchanged: the caller's input array, selected repository state, Files pane DOM, selected file state, websocket state, server workflow state, and browser URL.
- Calls: no first-party groom symbol; the layer bottoms out in JavaScript collection and string operations.
