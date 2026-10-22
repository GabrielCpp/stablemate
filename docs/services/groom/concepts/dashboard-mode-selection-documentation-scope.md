---
type: concept
slug: dashboard-mode-selection-documentation-scope
title: Dashboard mode selection documentation scope
---
# Dashboard mode selection documentation scope

`groom/groom/assets/dashboard.js::setMode` is the sole dispatch point for all five dashboard
activity modes. There is no alternate runtime implementation and no source-defined ranking
between the documentation nodes that describe it; each describes the same function from a
different entry point, and none supersedes another.

Use [Dashboard activity mode selection](dashboard-activity-mode-selection.md) for the complete
five-mode contract: the shared work every call performs, and the per-mode loader dispatch. Use
[Dashboard mode selection](dashboard-mode-selection.md) for the operator-facing question of
which mode to reach for and why the keyboard/palette flow forces Runs first. Use [Files and Diff
mode selection](files-and-diff-mode-selection.md) for the narrower Files/Diff pair, including
the loader-level detail — workspace file listing vs. working-tree diff parsing — that the other
two do not carry. All three describe the same function and must remain consistent rather than
being read as competing implementations.

- rule: use Dashboard activity mode selection for the complete five-mode contract, Dashboard
  mode selection for the operator-facing choice among all five modes, and Files and Diff mode
  selection for the narrower Files/Diff loader distinction; none is a different implementation
  or a deprecated alternative
