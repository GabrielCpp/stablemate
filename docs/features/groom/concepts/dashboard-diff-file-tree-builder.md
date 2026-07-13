---
type: concept
slug: dashboard-diff-file-tree-builder
title: dashboard diff file tree builder
---
# dashboard diff file tree builder

Dashboard diff file tree builder is the browser-side transformation used by [select activity diff mode](../gui/screens/groom-dashboard.md#select-activity-diff-mode) and [select repository menu option](../gui/screens/groom-dashboard.md#select-repository-menu-option) after [workspace diff data](../workspace-diff-data.md) has been parsed into the [dashboard parsed diff file cache](../dashboard-parsed-diff-file-cache.md). It converts parsed changed-file entries into the recursive [dashboard diff file tree](../dashboard-diff-file-tree.md) consumed by [diff directory toggle](../gui/screens/groom-dashboard.md#diff-directory-toggle) and [diff file row](../gui/screens/groom-dashboard.md#diff-file-row) components.

- code: groom/groom/templates/dashboard.html::buildFileTree

## Contract

- purpose: group flat Diff2Html parsed file entries into directory nodes and changed-file leaves for the Diff pane renderer.
- input: `Array<Diff2HtmlParsedFile>` from the [dashboard parsed diff file cache](../dashboard-parsed-diff-file-cache.md); current callers pass only non-empty arrays after rejecting empty response text and zero parsed files, but the builder itself also accepts an empty array and returns an empty root node.
- output: one [dashboard diff file tree](../dashboard-diff-file-tree.md) root node with `dirs` and `files` collections.
- path source: for each parsed entry, uses `newName` when it is truthy and not `/dev/null`; otherwise uses `oldName`.
- path coercion: converts the selected path value with JavaScript `String(...)` before splitting, so missing or null fallback values become literal display/grouping strings such as `undefined` or `null` rather than being rejected.
- path interpretation: `/` separates directory segments; every segment before the final segment is a directory name under the current parent, and the final segment is the displayed changed-file basename under that terminal node.
- index preservation: stores the original parsed-file array index on each file leaf so visually sorted rows can still select the correct cached parsed diff entry later.
- line counts: copies parser-supplied `addedLines` and `deletedLines` onto each file leaf for the generated row's visible `+N` and `-N` summary.
- duplicate handling: entries with the same selected path append independent file leaves to the same terminal node; no deduplication or overwrite occurs for file leaves.
- directory merging: repeated directory segments under the same parent reuse the same directory node so changed files sharing a directory prefix appear under one branch.
- ordering: preserves parsed-file order within each node's `files` collection while building nodes; visible directory and row sorting belongs to the renderer that consumes the tree.
- validation: does not reject duplicate paths, paths without directory separators, repeated slashes, dot segments, traversal-looking names, empty path segments, missing line-count values, or missing old/new names beyond JavaScript string coercion of the selected name.
- escaping: does not escape text for HTML; escaping belongs to the renderer that turns the tree into DOM strings.
- failure boundary: assumes `files` is array-like enough to provide `forEach` and that each item can be property-read as a parsed diff entry; invalid caller inputs may raise ordinary JavaScript runtime errors before any domain-specific error handling.

## Methods

### method-build-file-tree

- sig: `buildFileTree(files: Diff2HtmlParsedFile[]) -> DashboardDiffFileTree`
- abstract: false
- raises: no domain-specific errors for ordinary parsed diff entries; ordinary JavaScript runtime errors can surface if `files` is not iterable with `forEach` or if an entry is not property-readable.
- code: groom/groom/templates/dashboard.html::buildFileTree

Builds a fresh tree for one Diff pane load and returns it synchronously without reading or writing DOM state. For an empty `files` array, returns the initialized root with no child directories and no file leaves.

#### Effects

- Creates: a root [dashboard diff file tree](../dashboard-diff-file-tree.md) node initialized with empty `dirs` and `files` collections.
- Iterates: each parsed diff file entry in the array order supplied by the third-party parser.
- Selects: the grouping/display path from `newName` unless that value is falsey or `/dev/null`, otherwise from `oldName`.
- Coerces: the selected path to a string before splitting it into slash-delimited segments.
- Creates: a missing directory node for each directory segment along the selected path, each initialized with empty `dirs` and `files` collections.
- Reuses: an existing directory node when another changed file already created the same segment under the same parent.
- Appends: one changed-file leaf to the terminal node's `files` collection with the final path segment as `name`, the original parsed-file array position as `idx`, `addedLines` as `add`, and `deletedLines` as `del`; duplicate terminal names remain separate leaves.
- Leaves unchanged: the caller's parsed file array, individual parsed file objects, selected repository state, Diff pane DOM, selected changed-file state, websocket state, server workflow state, and browser URL.
- Calls: no first-party groom symbol; the layer bottoms out in JavaScript collection and string operations.
