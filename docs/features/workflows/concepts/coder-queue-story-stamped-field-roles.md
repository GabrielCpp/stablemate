---
type: concept
slug: coder-queue-story-stamped-field-roles
title: Coder queue story stamped field roles
---
# Coder queue story stamped field roles

`StoryStamped` reports the queue-integrity write performed by `stamp_story_passed`.
`stamped` answers whether that write recorded the story's `QA passed` line. The separate
`superseded_outcome` value answers whether that write replaced a previous attempt's outcome,
such as a give-up, documentation block, or interrupted run, rather than the `Not started` state
of a never-built story.

Neither field is an alternative implementation or a replacement for the other. Read `stamped`
when the caller needs to know whether the status write occurred; read `superseded_outcome` when
it needs to distinguish a prior-attempt outcome from an initial status. A caller can need both
facts, so the schema records both and defines no ranking between them.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryStamped`
- rule: use `stamped` for the status-write fact and `superseded_outcome` for the prior-attempt replacement fact; neither field supersedes the other
