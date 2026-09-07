---
type: concept
slug: work-counts-fields
title: Work counts fields
---
# Work counts fields

`WorkCounts` is one complete breakdown for the selected worklist scope, not a set of
alternative representations. `counts()` constructs every scalar and map in the same return
value: totals by lifecycle bucket, remaining work, the complete status distribution, and the
not-done category and kind compositions in `workhorse/workhorse/worklist.py::counts`.

Select the field that answers the needed question: use `total`, `done`, `active`, `blocked`,
`pending`, or `remaining` for a named lifecycle measure; use `by_status` for the full status
distribution; use `by_category` for a caller-selected payload category; and use `by_kind` for
the first-class kind composition. All fields are current complementary observations, so no
field supersedes or ranks above another.

- code: `workhorse/workhorse/worklist.py::WorkCounts`
- code: `workhorse/workhorse/worklist.py::counts`
- rule: select the field that answers the requested lifecycle measure or composition; no WorkCounts field is a replacement for another
