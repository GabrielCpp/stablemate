---
type: format
slug: code-review-result
title: Coder code review result
---
# Coder code review result

- file: none — in-memory agent reply
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult`
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- detail: [coder review finding](review-finding.md)

The feeder review reports the result of examining changed lines. Its status is required from the
agent; findings are structured `ReviewFinding` values and the summary explains either the issues
or why a blocked review could not inspect the diff.

## Fields

### status
- type: literal `findings`, `clean`, `skipped`, or `blocked`
- required: true
- semantics: whether the review found issues, checked a clean diff, had no affected changes, or could not read the diff
- verify: json_path(path="$.status", matches="findings|clean|skipped|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.status`
- detail: [code review status documentation](concepts/code-review-status-documentation.md)

### findings
- type: `list[ReviewFinding]`
- default: empty list
- required: false
- semantics: every review finding, empty unless status is `findings`
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings`
- detail: [coder code review findings field roles](concepts/coder-code-review-findings-field-roles.md)

### findings_summary
- type: `str`
- default: empty string
- required: false
- semantics: one-sentence account of flagged issues or the reason a blocked review stopped
- verify: json_path(path="$.findings_summary", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings_summary`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_the_review_lane_parses_the_loose_findings_it_used_to_declare`
- detail: [coder code-review findings summary context](concepts/coder-code-review-findings-summary-context.md)
