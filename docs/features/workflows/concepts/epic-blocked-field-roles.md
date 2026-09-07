---
type: concept
slug: epic-blocked-field-roles
title: Epic blocked field roles
---
# Epic blocked field roles

`workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked` records one
set-aside result. `epic_blocked` is the boolean outcome, `blocked_epics` is the comma-joined,
human-readable summary for the run record, and `reason` supplies the explanation when the result
is returned. The blocked set read by `select_epic` remains authoritative, so the summary is not a
branching input. No field is deprecated or replaces another.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked`
- rule: read `epic_blocked` for the set-aside outcome, `blocked_epics` for the run-record summary, and `reason` for its explanation; no field replaces another
