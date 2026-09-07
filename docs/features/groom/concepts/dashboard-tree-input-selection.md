---
type: concept
slug: dashboard-tree-input-selection
title: Dashboard tree input selection
---
# Dashboard tree input selection

The Files and Diff panes share the same browser tree builder while supplying it
with entries from different stages of their own flows. Neither format supersedes
the other: one is the Files pane's flat input and the other is the derived shape
the shared renderer walks.

Use [workspace file list data](../workspace-file-list-data.md) when the Files
pane has received repo-relative path strings from its `/files` response. The
Files pane wraps each string as a path entry before giving it to `buildTree`.

Use [dashboard path tree](../dashboard-path-tree.md) after `buildTree` has
grouped either Files-path entries or Diff parsed-file entries by their slash
segments. The shared renderer consumes this nested shape and receives a
pane-specific leaf renderer, so the tree does not select or describe either
pane's source data.

- code: groom/groom/assets/dashboard.js::buildTree
- rule: select workspace file list data as the Files pane's flat path input; select dashboard path tree only as the nested render-time result of `buildTree`; neither format is a replacement for the other.
