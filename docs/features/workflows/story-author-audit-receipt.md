---
type: format
slug: story-author-audit-receipt
title: Story author audit receipt
---
# Story author audit receipt

- The receipt is a JSON artifact written beside the selected story's `story.md` after the story has
  passed its audit. It binds the pass to the exact bytes judged by recording their SHA-256 digest.

- file: `<story directory>/audit-receipt.json`
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::AuditReceipt`
- detail: [author story-author subflow](concepts/author-story-author-subflow.md)
- tests: `workflows/tests/author/story_author/test_flow.py::test_flow_prepares_explicit_story_before_authoring_without_git_side_effects`

## Fields

### story_digest
- type: lowercase hexadecimal SHA-256 string
- default: empty string
- required: true
- semantics: digest of the exact current story document bytes at audit completion
- verify: json_path(path="$.story_digest", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::AuditReceipt`
- detail: [audit receipt field roles](concepts/audit-receipt-field-roles.md)

### path
- type: repository-relative string path
- default: empty string
- required: true
- semantics: path returned for the written `audit-receipt.json`
- verify: json_path(path="$.path", matches="audit-receipt\\.json$")
- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::AuditReceipt`
- detail: [audit receipt field roles](concepts/audit-receipt-field-roles.md)
