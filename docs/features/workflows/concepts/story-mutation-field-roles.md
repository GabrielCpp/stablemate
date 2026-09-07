---
type: concept
slug: story-mutation-field-roles
title: Story mutation field roles
---
# Story mutation field roles

`StoryMutation` reports the outcome of a standalone story graph edit. Its fields are complementary
parts of that outcome, not alternative representations. `changed` distinguishes a mutation from an
idempotent no-op; `epic` identifies the parent epic; `story_slug` identifies the story; `story_dir`
identifies its directory; `story_path` identifies its document; and `reason` explains the mutation
or no-op.

The schema declares each field directly with a `false` or empty-string default. It establishes no
deprecation, replacement, wrapper, or preference among them, so no field supersedes another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StoryMutation`
- rule: select the field for its named part of the mutation result; the six fields are complementary and no ranking exists
