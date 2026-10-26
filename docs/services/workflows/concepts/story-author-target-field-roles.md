---
type: concept
slug: story-author-target-field-roles
title: Story author target field roles
---
# Story author target field roles

`StoryTarget` declares independent fields for one caller-selected story and for the results of
preparing that story's document. Its source does not rank or supersede them: each field preserves
a distinct part of the selection or preparation result.

Use `epic` and `story` to identify the requested target, and `story_id` for the story's graph id
once preparation has resolved it. Use `epic_dir`, `story_dir`, or
`story_path` when the caller needs the corresponding repository-relative location. Use
`scaffolded` and `scaffold_message` to inspect whether preparation completed and what Ostler
reported. These fields are not alternative implementations and are carried together.

- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::StoryTarget` @67ca79f63e5f
- rule: select the field by the target representation or preparation outcome the caller requires; no field supersedes another
