---
type: concept
slug: milestone-context-field-roles
title: Milestone context field roles
---
# Milestone context field roles

`MilestoneContext` carries the repository and planning-graph snapshot needed before the
milestone authoring turn. Its fields are complementary state, not alternative implementations:
`repo_root` anchors filesystem access, `roadmap` identifies the approved source document,
`epics_dir` locates epic documents, and `milestone_path` identifies a reusable milestone when
one exists. `milestone_epics` preserves the pre-authoring epic order, while
`milestone_fingerprints` and `epic_fingerprints` preserve baselines for detecting changes to
milestones and epics respectively.

No ranking exists among these fields. Consumers use the representation required by their
operation; none replaces another.

- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- rule: use each field for its distinct repository, roadmap, path, ordered-epic, or fingerprint
  role; none supersedes another
