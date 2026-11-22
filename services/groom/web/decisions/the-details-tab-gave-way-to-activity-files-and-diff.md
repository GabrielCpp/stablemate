story: SM-01M6CN5GY6KBYPRS0ZKE7SRTH8
date: 2026-11-22
elements: RunDetail
sources: groom/groom/assets/dashboard.js, docs/milestones/0001-groom-run-visibility/milestone.md

The story asked for a run detail with two tabs, Overview and Details. The page has no Details tab, and the story keeps
that change. The milestone of the run visibility work retired the tab in a later epic, and the milestone outranks the
story. The run detail opens on Overview, and Activity sits beside it. A run with a diff and a sidecar adds Files and
Diff after Activity. The arrow keys move between the tabs.

Each record the Details tab showed has a new home. The state note of the run sits in the run head. Gas and pid sit in
the run facts of Overview, and the attendant link sits in the run head. The recent telemetry history is Activity with
its Raw chip, and the Raw chip carries the metric samples. The working-tree diff is the Diff tab. The open gates stay
above the tabs and can be answered there, whichever tab is open.

The book's groom has no run to select, so the screen names the two tabs that always show, Overview and Activity.
