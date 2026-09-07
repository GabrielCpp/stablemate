---
type: concept
slug: coder-queue-story-committed-field-roles
title: Coder queue story committed field roles
---
# Coder queue story committed field roles

`StoryCommitted` reports two independent facts about a passing story. They are not alternative
implementations and neither replaces the other.

`committed` answers whether implementation work landed in an affected repository. It excludes
the separate `QA passed` documentation-status stamp because every passing story writes that
stamp, including a rerun whose implementation work had already landed.

`superseded_outcome` answers whether that status stamp replaced a previous attempt's non-default
outcome, such as a give-up, documentation block, or interrupted run. It is false for a
never-attempted story, even when that story has no implementation commit.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::StoryCommitted`
- rule: read both fields together: use `committed` to identify implementation work and
  `superseded_outcome` to identify a passing status stamp that replaces an earlier attempt outcome
