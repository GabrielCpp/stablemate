---
type: format
slug: coverage-review-prompt
title: Coverage review prompt contract
---
# Coverage review prompt contract

The coverage-review turn is the semantic judge after deterministic seed coverage and graph checks
pass. It reads the epic's stated scope and acceptance, researched seed details including surfaces,
backing and prerequisites, the story coverage blocks, and each story's dependency DAG. Empty story
bodies are expected because body authoring happens later and are not findings.

The reviewer accepts only a split that reflects the complete epic scope, gives every story a
concrete and independently assessable deliverable, starts with a thin end-to-end journey step,
widens that path vertically, orders stories by real prerequisites, and gives every deferred scope
item an owner. It must flag coarse restore-everything stories, verify-only stories with no
deliverable, horizontal layer slices, false dependency edges, and unowned deferrals. It returns
`ok` when the topology passes, `gaps` with specific stories to add or split when bounded rework can
address the defect, and `blocked` with the product decision when coverage cannot be judged without
operator input. The turn reviews only; it does not edit artifacts.

- file: `workflows/src/workhorse_workflows/author/story_split/prompts/review-coverage.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::CoverageReview`
- detail: [author story-split subflow](concepts/story-split-subflow.md)
- tests: `workflows/tests/author/story_split/test_flow.py::test_coverage_findings_drive_a_bounded_resplit_worklist`

## Fields

### epic
- type: string
- required: true
- semantics: the single epic whose story split is judged
- verify: json_path(path="$.epic", matches=".+")

### epic_dir
- type: string path
- required: true
- semantics: canonical directory containing the epic document and all story documents under review
- verify: json_path(path="$.epic_dir", matches=".+")

### status
- type: string
- default: empty string
- required: true
- semantics: `ok` accepts the split, `gaps` requests named story rework, and `blocked` requires an operator decision
- verify: json_path(path="$.status", matches="^(ok|gaps|blocked)$")

### notes
- type: string
- default: empty string
- required: true
- semantics: adequacy rationale, specific stories to add or split, or the blocking question
- verify: json_path(path="$.notes", matches=".*")
