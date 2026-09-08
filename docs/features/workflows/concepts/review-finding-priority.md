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

- rule: use `must_fix_findings` for findings scored at least 80; use `advisory_findings` only as
  non-binding context for findings scored below 80
- prefers: [must fix findings](../coder-review-implementation-prompt.md#must_fix_findings)

## Methods

### split_on_confidence

- sig: `split_on_confidence(findings: Sequence[ReviewFinding]) -> tuple[list[ReviewFinding], list[ReviewFinding]]`
- does: partition findings with confidence >= 80 into the mandatory list
- verify: count(subject="mandatory", equals=1)
- does: partition findings with confidence < 80 into the advisory list
- verify: count(subject="advisory", equals=1)
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::split_on_confidence`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_split_is_inclusive_at_the_confidence_line`

### findings_block

- sig: `findings_block(findings: Sequence[ReviewFinding]) -> str`
- does: render findings as markdown for prompt inclusion when given a non-empty list
- verify: json_path(path="result", matches=".*Category.*")
- does: return "None." when given an empty list
- verify: json_path(path="result", equals="None.")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::findings_block`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_findings_block_says_none_rather_than_rendering_empty`
