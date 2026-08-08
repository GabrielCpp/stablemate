---
type: flow
slug: author-backlog-intake
title: Author backlog intake
---
# Author backlog intake

The author workflow turns a mutable human worklist into an identified, release-owned plan before an
agent decomposes any prose. The same normalization runs in epic mode and single-story mode, so a
manually added bullet is addressable on its first run without requiring a separate preparation
command.

- start: the target repository has the configured backlog file. It may contain existing bracketed
  items and unnamed bullets at any nesting level.
- steps:
  1. Author setup resolves the target repository and backlog path as checkpointed workflow context.
  2. Immediately before epic decomposition or single-story lookup, the intake node invokes
     `Ostler.backlog_adopt` against that resolved path.
   3. Ostler allocates full ids for every unnamed bullet while preserving prose and nesting. The
      backlog contract treats every bullet as work; context that should not receive identity is prose.
      Coder first attempts to drain items it files under `Filed by coder`; any that remain are ordinary
      author intake rather than a permanently separate ownership class.
  4. The author agent reads the normalized backlog and treats ids as opaque identities rather than
     deriving them from descriptions.
  5. For fresh release scope, the agent creates a milestone through Ostler with a generated id and
     the complete intake set in `sourceItems`. An external roadmap supplies its readable release
     boundary, title, epic membership, and order, but not an id copied from another graph.
  6. The agent reuses an active milestone only when the remaining intake is already owned and the
     product outcome is unchanged. It may extend that active milestone for overlapping new intake
     with the same outcome; disjoint work creates a new milestone, and completed milestones are
     never reopened.
  7. Review requires every backlog id to be owned by exactly one milestone and runs Ostler
     doctor before approving the plan.
- end: every backlog bullet has a durable full id, and one active generated-id
  milestone owns the intake that its ordered epics will drain.
- verify: workflows/tests/author/test_workflow.py::test_epic_mode_adopts_unnamed_scope_before_decomposition,
  workflows/tests/author/test_workflow.py::test_story_prune_preserves_a_parent_with_nested_work
- code: workflows/src/workhorse_workflows/author/nodes/intake.py::adopt_backlog
- code: workflows/src/workhorse_workflows/author/workflow.py::Author.start
- code: workflows/src/workhorse_workflows/author/workflow.py::Author.split_epics
- code: workflows/src/workhorse_workflows/author/nodes/coverage.py::prune_backlog
- code: workflows/src/workhorse_workflows/author/nodes/stories.py::prune_bullet
