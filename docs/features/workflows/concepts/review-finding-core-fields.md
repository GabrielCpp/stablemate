---
type: concept
slug: review-finding-core-fields
title: Review finding core fields
---
# Review finding core fields

`ReviewFinding` inherits these three fields from `Finding`: they form one actionable finding
rather than alternatives. `target` identifies where the defect is, `issue` states what is
wrong there, and `repair` names the smallest acceptable change. The router acts only when both
the target and repair are non-empty; `issue` supplies the explanation for that action.

No field supersedes another or is preferred independently. A complete review finding uses all
three roles together.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding`
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding`
- rule: use `target`, `issue`, and `repair` together to describe an actionable review finding
