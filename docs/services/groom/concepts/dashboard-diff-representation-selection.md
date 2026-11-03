---
type: concept
slug: dashboard-diff-representation-selection
title: Dashboard diff representation selection
---
# Dashboard diff representation selection

The dashboard carries one working-tree diff through two current representations. They are not
alternatives: the response keeps the raw unified text at the data boundary, while the Diff tab
parses that text into changed-file entries for its tree and selected-file viewer.

Use [workspace diff data](../formats/workspace-diff-data.md) when producing or consuming the sidecar
or HTTP payload. Use [dashboard parsed diff file cache](../formats/dashboard-parsed-diff-file-cache.md)
only in the Diff tab after `loadRunDiff` has received that payload: its parsed entries supply the
changed-file tree and let selecting a row render one already-parsed file without another request.
Keeping the payload raw avoids duplicating the browser parser on the producer, and keeping the
tab cache parsed avoids reparsing or fetching when an operator selects a changed file.

- code: groom/groom/assets/dashboard.js::loadRunDiff@6b1e2d0423d6
- rule: use raw workspace diff data at the sidecar and HTTP boundary; use the parsed file cache only for the Diff tab's changed-file selection and rendering
