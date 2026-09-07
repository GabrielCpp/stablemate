---
type: concept
slug: story-choice-field-roles
title: Story choice field roles
---
# Story choice field roles

`StoryChoice` is the single result returned by `select_story`; its properties describe different
parts of that result rather than alternative representations of it. The source declares each
property once with its own name and default, and declares no deprecation or preference among
them.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryChoice`
- rule: Read `has_story` to determine whether selection succeeded; use the path and slug fields
  to identify a selected story, and use `reason`, `progress`, and `remaining_count` to explain
  the selection state. No field supersedes another or has a source-defined ranking.
