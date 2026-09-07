---
type: concept
slug: epic-choice-field-roles
title: Epic choice field roles
---
# Epic choice field roles

`workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice` is one selection
result, not a set of alternative implementations. `has_epic` is the selection verdict; when it is
true, `epic` is the Ostler-resolved numbered directory name and `epic_dir` is the repository-relative
directory later nodes use. `reason` explains an empty queue, completed worklist, worklist read
failure, or selection, while `progress` carries the worklist snapshot for a completed or selected
result.

The model defaults every field, so an unsuccessful choice can carry only its reason and any available
progress. The selector sets `has_epic`, `epic`, `epic_dir`, `reason`, and `progress` together only
after it selects a pending item; it returns a reason-only choice when it cannot read or find work,
and adds progress when every item is complete. No field is deprecated or replaces another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_pick_epic`
- rule: read `has_epic` to determine whether a selection exists; when true, use `epic` with `epic_dir`, and use `reason` with `progress` to explain the selection or its absence; no field replaces another
