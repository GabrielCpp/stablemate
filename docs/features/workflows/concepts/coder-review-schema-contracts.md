---
type: concept
slug: coder-review-schema-contracts
title: Coder review schema contracts
---
# Coder review schema contracts

The `coder.shared.schemas.review` module defines the typed values the owner-turn flows share for
review: the finding a reviewer files, the context that says where review turns read, and the
inbox feedback an operator drops mid-run. The flow owns the context and feedback values, so they
carry conservative defaults.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::__all__` @818036e1a230
- detail: [coder finding](../formats/finding.md)
- detail: [coder result routing contract](coder-result-routing.md)
- detail: [coder review finding](../formats/review-finding.md)
- detail: [coder review context](../formats/review-context.md)
- detail: [coder review feedback](../formats/review-feedback.md)

`ReviewCategory` closes finding lenses to `Bug`, `Standard`, and `Reuse`.
