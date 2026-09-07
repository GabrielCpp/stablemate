---
type: concept
slug: impl-result-notes
title: Implementation result notes
---
# Implementation result notes

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.notes`
- rule: use the shared implementation-result field for the return contract; use the review apply prompt field when interpreting that same value for a review-application turn

`ImplResult.notes` is one shared field, not two implementations. Implement turns use it to
report what was implemented and verified; review apply turns use it to report what changed or
why the turn could not act. Both contexts accept the same optional string, defaulting to an
empty value, and neither is superseded. The source intentionally describes it for an
implement-or-apply turn, so no ranking applies.
