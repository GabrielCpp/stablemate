---
type: concept
slug: dashboard-activity-mode-selection
title: Dashboard activity mode selection
---
# Dashboard activity mode selection

`setMode` is the single dispatch point for all five dashboard activity modes — Runs, Files,
Diff, Telemetry, and Settings. It always performs the same shared work (record the mode on the
DOM and store, update the activity-bar button state, close the repository menu) and then, for
Files, Diff, and Telemetry only, calls that mode's loader. There is no legacy branch, no
feature flag, and no code path that treats one mode as superseding another.

[Dashboard mode selection](dashboard-mode-selection.md) documents the full five-mode contract:
the shared behaviour every call to `setMode` performs, and when an operator or the keyboard/
palette flow reaches for each of the five modes. [Files and Diff mode selection](files-and-diff-mode-selection.md)
documents the same function's behaviour for the Files/Diff pair specifically, including the
loader-level detail (workspace file listing vs. working-tree diff parsing) that the broader
document does not carry.

Neither document supersedes the other, and neither mode pair supersedes the other: this is one
function with five parallel, always-current branches, described at two levels of detail. A
reader who needs the full activity-bar contract reads the mode-selection concept; a reader who
only needs the Files/Diff pair's loader distinction reads the narrower one.

- code: groom/groom/assets/dashboard.js::setMode
- rule: no ranking exists between the five dashboard modes, and none between the Files/Diff pair; `setMode` treats every mode as a parallel, current alternative and dispatches to it unconditionally
- detail: [Dashboard mode selection documentation scope](dashboard-mode-selection-documentation-scope.md)
