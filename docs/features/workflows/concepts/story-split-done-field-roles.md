---
type: concept
slug: story-split-done-field-roles
title: Story split completion field roles
---
# Story split completion field roles

`StorySplitDone` is one terminal result for an epic whose story graph passed mechanical coverage
validation and semantic review. Its fields are complementary parts of that one result, not
alternative implementations. `status` records the terminal acceptance disposition; `epic` and
`epic_dir` identify the accepted epic and its canonical repository-relative directory;
`receipt_path` locates the digest-bound semantic-review receipt; and `coverage_reworks` and
`operator_resolutions` record the rework and operator-resolution turns used to reach acceptance.

The source declares these six attributes together on `StorySplitDone`, with `status` fixed to
`accepted` and both counters defaulting to zero. It declares no ranking or replacement among them:
consumers use each field for the distinct fact it carries.

- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone`
- rule: use every field for its distinct part of the accepted story-split result; no field is an alternative to another
