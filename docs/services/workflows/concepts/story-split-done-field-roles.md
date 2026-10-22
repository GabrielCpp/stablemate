---
type: concept
slug: story-split-done-field-roles
title: Story split completion field roles
---
# Story split completion field roles

`StorySplitDone` is one terminal result for an epic's story split. Its fields are complementary
parts of that one result, not alternative implementations. `status` records the disposition,
`accepted` when the story graph passed the lint and the PM review and `blocked` when a budget ran
out. `epic` and `epic_dir` identify the epic and its canonical repository-relative directory.
`notes` carries the reason a blocked split stopped. `reworks` and `answers` record the rework and
PM-answer turns used.

The source declares these six attributes together on `StorySplitDone`, with `status` defaulting to
`accepted` and both counters defaulting to zero. It declares no ranking or replacement among them:
consumers use each field for the distinct fact it carries.

- code: `workflows/src/workhorse_workflows/author/story_split/schemas.py::StorySplitDone` @3d9f15f6170b
- rule: use every field for its distinct part of the split result; no field is an alternative to another
