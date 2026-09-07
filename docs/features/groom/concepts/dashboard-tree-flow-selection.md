---
type: concept
slug: dashboard-tree-flow-selection
title: Dashboard tree flow selection
---
# Dashboard tree flow selection

The Files and Diff journeys are separate current uses of the same browser-side
tree builder and directory control, not alternative ways to perform one task.
Use the Files journey when an operator needs to browse and open workspace file
content. Use the Diff journey when an operator needs to inspect changed files
and their rendered working-tree diff.

Both paths call the builder with path-carrying entries, but their leaves retain
the caller's entry object. Files supplies paths from its workspace-file-list
response; Diff supplies parsed diff entries with the index and line counts its
viewer needs. The shared builder therefore provides the same nested display
without choosing a pane, data source, or file rendering behaviour. Each
directory node is rendered by `TreeDir`, whose button flips only that node's
component-local open state; the Files and Diff trees pass it different leaf
renderers, not different directory-toggle implementations.

- code: groom/groom/assets/dashboard.js::buildTree
- code: groom/groom/assets/dashboard.js::TreeDir
- rule: use the Files directory toggle while browsing workspace files and the Diff directory toggle while inspecting working-tree changes; neither is preferred because `TreeDir` implements the same local directory expansion for both panes.
