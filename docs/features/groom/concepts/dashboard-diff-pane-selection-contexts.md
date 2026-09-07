---
type: concept
slug: dashboard-diff-pane-selection-contexts
title: Dashboard Diff Pane Selection Contexts
---
# Dashboard Diff Pane Selection Contexts

Selecting the Diff activity mode and selecting a changed-file row are consecutive controls in one
Diff-pane journey, not alternative implementations of the same selection. The activity control
sets the dashboard mode to `diff` and starts the diff load. `DiffTree` then renders the parsed
changed-file entries. A file-row selection writes that entry's index, which `DiffView` uses to
render the one selected file without another request.

Use the activity control when opening the working-tree Diff pane. Use a changed-file row only
after the pane has loaded changed files, to choose which already-parsed file the viewer shows.
Neither interaction is ranked or deprecated: each is required in its own stage of the journey.

- code: groom/groom/assets/dashboard.js::DiffTree
- rule: open the Diff pane with its activity control, then select a changed-file row to choose the parsed file rendered in that pane; neither interaction replaces the other
