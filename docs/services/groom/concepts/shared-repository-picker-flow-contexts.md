---
type: concept
slug: shared-repository-picker-flow-contexts
title: Shared repository picker flow contexts
---
# Shared repository picker flow contexts

The Files and Diff journeys use the same repository picker because both need the
same container and checkout selection. Selecting an option records that shared
selection, updates every picker label, and loads the pane for the dashboard's
current mode.

Neither journey is preferred or deprecated. Use the workspace-file journey when
the operator needs to browse a file's content; use the working-tree-diff journey
when the operator needs to inspect changed files. The shared picker does not
choose between those purposes: its caller's active mode determines whether
`loadFiles` or `loadDiff` runs after selection.

- code: groom/groom/assets/dashboard.js::openRepoMenu
- rule: use the Files flow to browse workspace file content and the Diff flow to inspect working-tree changes; after either flow selects a repository, load the pane for the active dashboard mode
