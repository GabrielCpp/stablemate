---
type: concept
slug: coder-queue-story-branch-field-roles
title: Coder queue story branch field roles
---
# Coder queue story branch field roles

`StoryBranch` records one completed story-branch operation. Its three fields are complementary,
not alternative implementations: `base_branch` identifies the branch read before the cut,
`story_branch` names the branch for the story, and `repos` records the workspace repositories
actually branched, with the documentation root first. The schema declares all three directly and
does not mark any as legacy, delegated, or preferred.

Read all three fields when the branch operation's context, result, and affected repositories are
needed. No field ranks above or replaces another; use the field whose distinct result fact is
needed.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryBranch`
- rule: select the field for the distinct branch-operation fact needed; no ranking or replacement exists among `base_branch`, `story_branch`, and `repos`
