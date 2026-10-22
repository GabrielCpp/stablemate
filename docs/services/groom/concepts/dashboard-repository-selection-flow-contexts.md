---
type: concept
slug: dashboard-repository-selection-flow-contexts
title: Dashboard repository selection flow contexts
---
# Dashboard repository selection flow contexts

The shared repository menu records the chosen container, checkout directory, and
label before it dispatches the current dashboard pane. It does not choose a
workflow journey: Files and Diff are both current contexts for the same
selection action.

Use workspace-file browsing when the operator needs repository file content.
Use working-tree diff inspection when the operator needs changed-file output.
After either journey selects a repository, the active dashboard mode determines
whether the client loads Files or Diff; neither flow supersedes the other.

- code: groom/groom/assets/dashboard.js::selectRepo
- rule: use workspace-file browsing for repository file content and working-tree diff inspection for changed-file output; repository selection dispatches the pane matching the active dashboard mode, with neither flow preferred or deprecated
