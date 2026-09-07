---
type: format
slug: milestone-context
title: Milestone context
---
# Milestone context

The in-memory context captures the approved roadmap identity and the planning-graph state before
the agent turn. Repository paths are strings; fingerprint maps use repository-relative milestone
paths or epic names as keys and SHA-256 digests as values. Empty defaults represent that no
roadmap-owned milestone or epics existed at preparation time.

- file: none — in-memory Pydantic model
- config: none
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [author milestone subflow](concepts/author-milestone-subflow.md)
- tests: `workflows/tests/author/milestone/test_flow.py::test_builds_then_reuses_one_milestone_without_epics`

## Fields

### repo_root
- type: string
- default: no default
- verify: json_path(path="$.repo_root", matches="^/.+")
- default: supplied by repository discovery
- required: true
- semantics: absolute repository root used for all milestone reads and writes
- verify: json_path(path="$.repo_root", matches="^/.+")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### roadmap
- type: string
- default: no default
- verify: json_path(path="exception.type", equals="ValidationError")
- default: supplied by approved-roadmap resolution
- verify: json_path(path="$.roadmap", matches=".+")
- required: true
- semantics: repository-relative approved roadmap path that must own exactly one milestone
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### epics_dir
- type: string
- default: no default
- verify: json_path(path="$.epics_dir", matches=".+")
- default: supplied by author path resolution
- verify: json_path(path="$.epics_dir", matches=".+")
- required: true
- semantics: repository-relative directory containing epic documents
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### milestone_path
- type: string
- default: empty string when the roadmap has no existing milestone
- required: false
- semantics: repository-relative path of the existing roadmap-owned milestone, when reused
- verify: json_path(path="$.milestone_path", equals="")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### milestone_epics
- type: list of strings
- default: empty list
- required: false
- semantics: ordered epic identifiers captured before authoring and preserved by validation
- verify: json_path(path="$.milestone_epics", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### milestone_fingerprints
- type: dictionary of relative milestone path to SHA-256 digest
- default: empty dictionary
- required: false
- semantics: baseline used to detect edits to unrelated milestones
- verify: json_path(path="$.milestone_fingerprints", matches="^\\{\\}$")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)

### epic_fingerprints
- type: dictionary of epic name to SHA-256 digest
- default: empty dictionary
- required: false
- semantics: baseline used to reject epic creation or modification during milestone authoring
- verify: json_path(path="$.epic_fingerprints", matches="^\\{\\}$")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneContext`
- detail: [milestone context field roles](concepts/milestone-context-field-roles.md)
