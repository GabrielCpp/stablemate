---
type: concept
slug: dashboard-diff-representation-selection
title: Dashboard diff representation selection
---
# Dashboard diff representation selection

The dashboard carries one working-tree diff through two current representations. They are not
alternatives: the response keeps the raw unified text at the data boundary, while the Diff pane
parses that text into changed-file entries for its tree and selected-file viewer.

Use [workspace diff data](../workspace-diff-data.md) when producing or consuming the sidecar,
HTTP, or run-detail disclosure payload. The disclosure renders the whole raw diff when it opens
and does not need file selection state. Use [dashboard parsed diff file cache](../dashboard-parsed-diff-file-cache.md)
only in the Diff pane after `loadDiff` has received that payload: its parsed entries supply the
changed-file tree and let selecting a row render one already-parsed file without another request.
Keeping the payload raw avoids duplicating the browser parser on the producer, and keeping the
pane cache parsed avoids reparsing or fetching when an operator selects a changed file.

- code: groom/groom/assets/dashboard.js::loadDiff
- rule: use raw workspace diff data at the sidecar, HTTP, and whole-disclosure boundary; use the parsed file cache only for the Diff pane's changed-file selection and rendering
