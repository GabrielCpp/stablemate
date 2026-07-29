---
type: format
slug: dashboard-path-tree
title: Dashboard path tree
---
# Dashboard path tree

Dashboard path tree is the browser-local recursive shape produced by the
[dashboard tree builder](concepts/dashboard-tree-builder.md) and walked by the
dashboard's shared tree renderer. One shape serves both panes: the Files pane
builds it from [workspace file list data](workspace-file-list-data.md) paths and the
Diff pane from the [dashboard parsed diff file cache](dashboard-parsed-diff-file-cache.md),
and the renderer that turns it into [files directory toggle](gui/screens/groom-dashboard.md#files-directory-toggle),
[diff directory toggle](gui/screens/groom-dashboard.md#diff-directory-toggle),
[files file row](gui/screens/groom-dashboard.md#files-file-row) and
[diff file row](gui/screens/groom-dashboard.md#diff-file-row) components cannot tell
which pane it is serving except through the leaf renderer it was handed.

It is not on the wire. No endpoint returns it, no websocket frame carries it, and it
is never persisted — the server sends flat paths and this shape is derived from them
in the browser, per render, for one pane.

- file: not an on-disk artifact; this is an in-memory browser object derived per render.
- code: groom/groom/assets/dashboard.js::buildTree
- verify: groom/tests/test_tree_builder.py::test_flat_paths_become_directory_nodes_and_file_leaves
- verify: groom/tests/test_tree_builder.py::test_an_empty_entry_list_yields_an_empty_root

## Contract

- producer: the [dashboard tree builder](concepts/dashboard-tree-builder.md), and nothing else.
- consumer: the shared tree renderer, which receives a root node and a pane-supplied leaf renderer.
- lifetime: one tree per render of a non-empty Files or Diff tree. It is derived from the store slice rather than stored in it, so a re-render rebuilds it and no invalidation step exists to get wrong.
- scope: one selected container and repository, in one tab.
- root: a node with the same shape as every directory node. It has no name and is not itself rendered as a directory row.
- node invariant: every node has both `dirs` and `files`. No node carries its own name, a parent pointer, a full path, open/collapsed state, selection state, or rendered markup.
- leaf invariant: every leaf has exactly `name` and `entry`. It carries no children, no selected state, no file content, and no response metadata.
- collapse state: not here. A directory's open/closed state is local to that directory's component in that tab, keyed by name so it survives re-renders, and is deliberately kept out of both this shape and the client store — nothing else reads it.
- selection state: not here either. The Files pane holds the selected path and the Diff pane the selected index, both in the client store; a leaf renderer compares against that to mark itself current.
- ordering: the shape preserves insertion order. The renderer sorts directory keys, and sorts a *copy* of each node's `files` by `name`, at render time — the node itself is never reordered in place.
- duplicate rule: duplicate paths appear as separate leaves under the same node; nothing is merged.
- escaping: raw strings are retained and no escaping is applied or needed, because every one of them reaches the document as a text child rather than as markup.

## Fields

### field-dirs

- type: object keyed by directory-segment name, each value another node of this shape.
- default: `{}`
- required: true
- meaning: the child directories of this node. Insertion-ordered; the renderer sorts the keys for display.

### field-files

- type: array of leaf objects.
- default: `[]`
- required: true
- meaning: the entries whose final path segment sits directly under this node.

### field-leaf-name

- type: string
- required: true
- wire-key: `name`
- meaning: the final `/`-delimited segment of the entry's path — the label the row displays.

### field-leaf-entry

- type: the caller's entry object, by reference.
- required: true
- wire-key: `entry`
- meaning: whatever the pane put in. The Files pane's carries `path`; the Diff pane's carries `path`, the parsed file's `idx`, and its `add` and `del` line counts. The renderer never reads it — only the pane's own leaf renderer does.
