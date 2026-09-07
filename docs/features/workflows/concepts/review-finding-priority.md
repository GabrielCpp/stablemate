---
type: concept
slug: review-finding-priority
title: Review finding priority
---
# Review finding priority

The implementation reviewer receives both finding blocks. It uses `must_fix_findings` to identify
repairs that the review requires, while `advisory_findings` supplies lower-confidence context for
its judgment and cannot itself require a change. Both remain current because every feeder finding
is rendered into exactly one block according to its score.

- code: `workflows/src/workhorse_workflows/coder/review/flow.py::findings_block`
- rule: use `must_fix_findings` for findings scored at least 80; use `advisory_findings` only as
  non-binding context for findings scored below 80
- prefers: [must fix findings](../coder-review-implementation-prompt.md#must_fix_findings)
