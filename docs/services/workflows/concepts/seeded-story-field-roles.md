---
type: concept
slug: seeded-story-field-roles
title: Seeded story field roles
---
# Seeded story field roles

`workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` reports the
result of registering one register record as a story. Its fields are complementary
attributes, not alternate implementations: `epic_dir` identifies the receiving epic directory;
`story_slug`, `story_dir`, and `story_path` identify the created or reused story; `record_id`
identifies the register record the story came from; and `reason` explains why the result was
created or reused.

The schema declares each field directly with an empty-string default. It establishes
no deprecation, replacement, wrapper, or preference among them, so no field supersedes another.
Select the field for the corresponding part of the seeded-story result; readers commonly need
the story identity together with its origin and outcome rationale.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::SeededStory` @c0c7fb10e846
- rule: select each field for its named part of the seeded-story result; the six fields are complementary and no ranking exists
