---
type: format
slug: story-split-receipt
title: Story split review receipt
---
# Story split review receipt

The receipt is a JSON artifact written beside an epic's `epic.md` after semantic coverage review.
It binds the passing review to the exact active-seed and story topology digest, so later story
prose edits do not invalidate a review that covers only split-owned structure.

- file: `<epic directory>/story-split-receipt.json`
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitReceipt`
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Fields

### graphDigest
- type: lowercase hexadecimal SHA-256 string
- required: true
- semantics: digest of active seed identities and each story's slug, title, covered seed items, and dependencies
- verify: json_path(path="$.graphDigest", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::story_split_digest`

### path
- type: repository-relative string path
- required: true
- semantics: path returned to the flow for the written receipt artifact
- verify: json_path(path="$.path", matches="story-split-receipt\\.json$")
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitReceipt`

The on-disk JSON uses `status: "passed"` and camel-case `graphDigest`; the typed return uses
`graph_digest` and does not duplicate the persisted status.
