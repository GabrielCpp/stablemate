---
type: format
slug: story-split-receipt
title: Story split review receipt
---
# Story split review receipt

The receipt is a JSON artifact written beside an epic's `epic.md` after semantic coverage review.
It binds the passing review to the exact active-seed and story topology digest, so later story
prose edits do not invalidate a review that covers only split-owned structure. The persisted JSON
contains only the review status and camel-case graph digest; the returned `StorySplitReceipt`
value additionally carries the repository-relative receipt path.

- file: `<epic directory>/story-split-receipt.json`
- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitReceipt`
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`

## Methods

### story_split_digest
- sig: `story_split_digest(epic: Epic) -> str`
- does: includes the ids of active seeds in the digest input
- verify: count(subject="active seeds in story split digests", equals=1)
- does: includes each story slug, title, covered seed items, and dependencies in the digest input
- verify: count(subject="story topology in split digests", equals=1)
- does: serializes the digest input with sorted keys and compact separators before hashing
- verify: json_path(path="$.graphDigest", matches="^[0-9a-f]{64}$")
- returns: a deterministic lowercase SHA-256 hexadecimal digest of the split-owned topology
- verify: json_path(path="$.graphDigest", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::story_split_digest`

### story_split_receipt_path
- sig: `story_split_receipt_path(epic: Epic) -> Path | None`
- does: places `story-split-receipt.json` beside the epic document when the epic has a persisted document
- verify: json_path(path="$.path", matches="story-split-receipt\\.json$")
- returns: the receipt path, or null when the epic has no epic document
- verify: count(subject="story split receipt path results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::story_split_receipt_path`

### story_split_review_current
- sig: `story_split_review_current(epic: Epic) -> bool`
- does: returns false when no persisted epic document or receipt exists
- verify: count(subject="missing story split receipts", equals=1)
- does: returns false when the receipt cannot be read or its contents are not valid JSON
- verify: count(subject="unreadable story split receipts", equals=1)
- does: returns false when the receipt status is not exactly `passed`
- verify: count(subject="non-passed story split receipts", equals=1)
- does: returns false when the receipt graph digest differs from the current topology digest
- verify: count(subject="stale story split reviews", equals=1)
- returns: true only when the receipt status is `passed` and its graph digest equals the current topology digest
- verify: count(subject="current story split reviews", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::story_split_review_current`

### RECEIPT_NAME
- sig: `RECEIPT_NAME: str`
- returns: the filename `story-split-receipt.json` used beside an epic document
- verify: count(subject="story split receipt filenames", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::RECEIPT_NAME`

## Fields

### status
- type: string literal
- required: true
- semantics: review result that must be `passed` for the receipt to be current
- verify: json_path(path="$.status", equals="passed")
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/review.py::record_story_split_review`

### graphDigest
- type: lowercase hexadecimal SHA-256 string
- required: true
- semantics: digest of active seed identities and each story's slug, title, covered seed items, and dependencies
- verify: json_path(path="$.graphDigest", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/author/shared/story_split_receipt.py::story_split_digest`

The on-disk JSON uses `status: "passed"` and camel-case `graphDigest`. The typed
`StorySplitReceipt` return uses `graph_digest` and a repository-relative `path`; neither is an
additional persisted JSON field.
