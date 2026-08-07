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
  items and direct unnamed bullets under second-level sections.
- steps:
  1. Author setup resolves the target repository and backlog path as checkpointed workflow context.
  2. Immediately before epic decomposition or single-story lookup, the intake node invokes
     `Ostler.backlog_adopt` against that resolved path.
  3. Ostler allocates full ids for eligible unnamed direct bullets. It preserves existing ids and
     prose, nested detail bullets, preamble bullets, and coder-filed discoveries.
  4. The author agent reads the normalized backlog and treats ids as opaque identities rather than
     deriving them from descriptions.
  5. For fresh release scope, the agent creates a milestone through Ostler with a generated id and
     the complete intake set in `sourceItems`. An external roadmap supplies its readable release
     boundary, title, epic membership, and order, but not an id copied from another graph.
  6. The agent reuses an active milestone only when the remaining intake is already owned and the
     product outcome is unchanged. It may extend that active milestone for overlapping new intake
     with the same outcome; disjoint work creates a new milestone, and completed milestones are
     never reopened.
  7. Review requires every eligible backlog id to be owned by exactly one milestone and runs Ostler
     doctor before approving the plan.
- end: every decomposable backlog bullet has a durable full id, and one active generated-id
  milestone owns the intake that its ordered epics will drain.
- verify: workflows/tests/author/test_workflow.py::test_epic_mode_adopts_unnamed_scope_before_decomposition
- code: workflows/src/workhorse_workflows/author/nodes/intake.py::adopt_backlog
- code: workflows/src/workhorse_workflows/author/workflow.py::Author.start
- code: workflows/src/workhorse_workflows/author/workflow.py::Author.split_epics
