---
type: concept
slug: review-verdict-notes-context
title: Review verdict notes context
---
# Review verdict notes context

`ReviewVerdict.notes` is the single notes field returned by the binding implementation review.
The schema calls it the brief passed to downstream turns; for a blocked verdict it carries the
external dependency and attempted resolution.

Use the review-verdict field for the shared response contract. Use the coder
review-implementation-prompt field when preparing or interpreting the implementation review
prompt's coverage of automated, reuse, and self-review findings. The source establishes neither
document as a replacement for the other, so no preference or deprecation applies.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.notes`
- rule: use the verdict field for the shared response contract and the prompt field for implementation-review prompt context; neither is ranked above the other
