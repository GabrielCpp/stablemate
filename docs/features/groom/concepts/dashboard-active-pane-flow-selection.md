---
type: concept
slug: dashboard-active-pane-flow-selection
title: Dashboard active-pane flow selection
---
# Dashboard active-pane flow selection

The shared active-pane loader has two current callers after repository selection. The workspace-file
flow reaches it while the dashboard mode is `files`; the working-tree-diff flow reaches it while the
mode is `diff`. Neither is a replacement for the other.

The loader selects the pane loader from the current mode: it invokes the Files loader for `files` and
the Diff loader for `diff`. It takes no action for other modes, so a repository choice only reloads
the currently active Files or Diff pane rather than both panes.

- code: groom/groom/assets/dashboard.js::loadActivePane
- rule: use the workspace-file flow in Files mode and the working-tree-diff flow in Diff mode; neither flow is ranked over the other
