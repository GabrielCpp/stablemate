---
type: concept
slug: seeded-story-field-roles
title: Seeded story field roles
---
# Seeded story field roles

`workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` reports the
result of registering one backlog or literal bullet as a story. Its fields are complementary
attributes, not alternate implementations: `epic_dir` identifies the receiving epic directory;
`story_slug`, `story_dir`, and `story_path` identify the created or reused story; `bullet_id`
identifies the input bullet; `from_backlog` records whether that input came from the configured
backlog; and `reason` explains why the result was created or reused.

The schema declares each field directly with an empty-string or `false` default. It establishes
no deprecation, replacement, wrapper, or preference among them, so no field supersedes another.
Select the field for the corresponding part of the seeded-story result; readers commonly need
the story identity together with its origin and outcome rationale.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory`
- rule: select each field for its named part of the seeded-story result; the seven fields are complementary and no ranking exists
