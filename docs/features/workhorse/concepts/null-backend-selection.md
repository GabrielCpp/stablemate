---
type: concept
slug: null-backend-selection
title: NullBackend selection
---
# NullBackend selection

Use `NullBackend` only as the internal backend for a run with no selected agent CLI, such as a
dry run or a workflow that drives script nodes only. A run with a selected CLI uses that CLI's
registered backend instead. `NullBackend` is not itself a selectable CLI: its `none` name is for
diagnostic errors, it has no model or session compaction capability, and an agent turn reports
that the operator must select a CLI.

- code: `workhorse/workhorse/runner/backends/null.py::NullBackend`
- rule: use `NullBackend` only when no agent CLI was selected; otherwise use the selected CLI's registered backend
- prefers: [null-backend](null-backend.md)
- detail: [Agent backend selection](agent-backend-selection.md)
