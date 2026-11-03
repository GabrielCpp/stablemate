---
type: concept
slug: dashboard-activity-mode-selection
title: Dashboard activity mode selection
---
# Dashboard activity mode selection

`setMode` is the single dispatch point for all five dashboard activity modes: Runs, History, Attend,
Dispatch and Settings. It always performs the same shared work (record the mode on the DOM and
store, update the activity-bar button state, stop the dispatch poll when leaving Dispatch and the history poll when leaving History) and
then, for History, Attend, Dispatch and Settings only, calls that mode's loader. A mode whose pane is not in
the page falls back to Runs, so a remembered mode that no longer exists never leaves a blank pane.
There is no legacy branch, no feature flag, and no code path that treats one mode as superseding
another.

[Dashboard mode selection](dashboard-mode-selection.md) documents the operator-facing contract:
when an operator or the keyboard and palette flow reaches for each of the five modes.

- code: groom/groom/assets/dashboard.js::setMode@11d392c3f50b
- rule: no ranking exists between the five dashboard modes; `setMode` treats every mode as a parallel, current alternative and dispatches to it unconditionally, and a mode with no pane lands on Runs
