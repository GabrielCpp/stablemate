---
type: concept
slug: story-snapshot-field-roles
title: Story snapshot field roles
---
# Story snapshot field roles

`StorySnapshot` captures one story's identity, metadata, source location, body identity, and edit
protection. Its fields are complementary parts of that snapshot, not alternative implementations:
`slug` identifies the story; `title` and `status` carry its metadata; `covers` and `depends` carry
its graph relationships; `story_path` locates its document; `body_hash` identifies its body; and
`frozen` records whether the edit plan may change it.

The schema declares every field directly with its own type and default. Snapshot construction
populates the fields together from a story record, and projection retains the fields that an edit
does not replace. There is no legacy marker, delegation, wrapper, or preference between fields, so
no field supersedes another. Select each field by the story attribute needed; combine fields when
the operation needs multiple snapshot attributes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StorySnapshot`
- rule: select fields by the story attribute needed; the fields are complementary and no ranking exists
