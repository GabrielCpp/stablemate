---
type: concept
slug: story-change-field-roles
title: Story change field roles
---
# Story change field roles

`StoryChange` projects one story mutation. Its fields are complementary parts of that projection,
not alternative implementations: `action` selects the structural operation; `slug` identifies the
story; `title`, `covers`, and `depends` carry the resulting story metadata; and `rewrite` records
whether the story body requires replacement after graph application.

The schema declares every field directly with its own type and default. It has no legacy marker,
delegation, wrapper, or preference between fields, so no field supersedes another. Select the
field that represents the story attribute a projected change carries; combine fields when one
change needs multiple attributes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::StoryChange`
- rule: select fields by the story attribute a projected change carries; the fields are complementary and no ranking exists
