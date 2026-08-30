---
type: flow
slug: author-roadmap-intake
title: Author roadmap intake
---
# Author roadmap intake

The author workflow turns one approved release contract into exactly one milestone of ordered epics
and vertical stories. The roadmap remains durable; Author never copies it into or prunes it as a
mutable worklist.

- start: the caller names one `docs/roadmaps/*.md` file with `type: roadmap` and `status: approved`.
- steps:
  1. Setup resolves the explicit path and rejects missing files, paths outside `docs/roadmaps/`,
     non-roadmap frontmatter, and every status except `approved`.
  2. Decomposition creates or resumes one generated-id milestone and records the canonical roadmap
     path as that milestone's sole `sourceItems` value.
  3. The agent orders one or more journey-based epics inside the milestone. Internal phases, layers,
     migrations, and rollout steps remain inside that release boundary.
  4. A deterministic gate rejects zero or multiple owning milestones, additional source items, and
     an empty epic list before per-epic authoring begins.
  5. Author writes epic seeds and vertical stories, validates coverage and graph integrity, and never
     reads or prunes the repository backlog during epic mode.
  6. Only after final artifact validation passes does Author advance the roadmap from `approved` to
     `authored` and commit the roadmap with its generated planning graph.
- end: the authored roadmap is the durable source of exactly one milestone whose ordered epics and
  stories are ready for Coder.
- verify: workflows/tests/author/test_workflow.py::test_epic_mode_authors_one_roadmap_milestone_and_commits_it
- verify: workflows/tests/author/test_config.py::test_roadmap_must_source_exactly_one_nonempty_milestone
- code: workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config
- code: workflows/src/workhorse_workflows/author/main/nodes/intake.py::validate_roadmap_milestone
- code: workflows/src/workhorse_workflows/author/main/nodes/intake.py::mark_roadmap_authored
- code: workflows/src/workhorse_workflows/author/main/flow.py::Author.split_epics
