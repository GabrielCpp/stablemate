---
type: concept
slug: story-author-done-field-roles
title: Story author completion field roles
---
# Story author completion field roles

`StoryAuthorDone` reports one completed directly invoked story-author run. Its fields are
complementary dimensions of that result, not alternative implementations: `status` identifies
the outcome, `epic` and `story` identify the authored work, `story_path` locates its document,
`mockup` and `notes` carry optional authoring context, and `reworks` and `answers` count the rework and PM-answer turns used.

No field supersedes another. Consumers read the field that answers the result dimension they
need and may combine fields when they need both identity, location, outcome, or context.

- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryAuthorDone` @67ca79f63e5f
- rule: select the field by the result dimension required; no `StoryAuthorDone` field is a replacement for another
