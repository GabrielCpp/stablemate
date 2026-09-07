---
type: concept
slug: coder-queue-worktree-cleanliness-field-roles
title: Coder queue worktree cleanliness field roles
---
# Coder queue worktree cleanliness field roles

`WorktreeCleanliness` records one post-development-gate result as complementary fields, not
alternative ways to represent cleanliness. No field is preferred or deprecated.

Read `clean` for the summary decision: it is true only when no story-owned uncommitted paths
remain. When it is false, read `dirty` for the repository-qualified paths still uncommitted;
these exclude paths that were dirty before the story and that the story did not later touch.
Read `repos` to identify the repositories inspected for that story, regardless of whether any
qualifying dirty paths remain.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::WorktreeCleanliness`
- rule: read `clean` as the outcome, `dirty` as the qualifying path evidence when the outcome is false, and `repos` as the inspection scope; the fields are complementary and have no ranking
