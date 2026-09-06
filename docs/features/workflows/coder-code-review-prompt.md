---
type: format
slug: coder-code-review-prompt
title: Coder code-review prompt
---
# Coder code-review prompt

- file: `workflows/src/workhorse_workflows/coder/review/prompts/code-review.md`
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`
- detail: [coder review flow](flows/coder-review.md)
- detail: [coder review schema contracts](concepts/coder-review-schema-contracts.md)
- tests: `workflows/tests/coder/review/test_flow.py::test_the_reviewers_run_in_the_docs_repo_and_see_the_code_repos`

The feeder turn reviews only the local changes in each supplied repository. It may inspect an
open pull request, but the working-tree or branch diff remains the review target. It reports all
findings with an actionable location and repair, and tags each finding with the lens that found it.
The flow later separates scores at 80; the prompt does not discard low-confidence findings.

## Fields

### story_path
- type: `str path`
- required: true
- semantics: story document whose scope the review uses
- verify: json_path(path="$.story_path", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`

### affected_repo_paths
- type: `list[str path]`
- required: true
- semantics: repositories whose local changes are reviewed
- verify: json_path(path="$.affected_repo_paths", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`

### branch
- type: `str`
- default: empty string
- required: false
- semantics: branch to inspect when the review is branch-scoped; omitted means use the current branch
- verify: json_path(path="$.branch", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`

### pr_number
- type: `str`
- default: empty string
- required: false
- semantics: optional pull request number whose state is checked and to which findings may be posted
- verify: json_path(path="$.pr_number", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.start`

### status
- type: `Literal[findings, clean, skipped, blocked]`
- required: true
- semantics: whether findings were found, the reviewed diff was clean, no changes existed, or the diff could not be read
- verify: json_path(path="$.status", matches="^(findings|clean|skipped|blocked)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.status`

### findings
- type: `list[ReviewFinding]`
- default: empty list
- required: false
- semantics: every reported issue, including advisory findings, each with target, issue, repair, category, and score
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings`

### findings_summary
- type: `str`
- default: empty string
- required: false
- semantics: one-sentence summary of findings or the reason a blocked diff could not be reviewed
- verify: json_path(path="$.findings_summary", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::CodeReviewResult.findings_summary`

## Fields: ReviewFinding

### target
- type: `str`
- default: empty string
- required: true
- semantics: repository location or other precise review target
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.target`

### issue
- type: `str`
- default: empty string
- required: true
- semantics: defect identified at the target
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.issue`

### repair
- type: `str`
- default: empty string
- required: true
- semantics: smallest change that resolves the finding
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.repair`

### category
- type: `Literal[Bug, Standard, Reuse]`
- required: true
- semantics: review lens that found the issue; Reuse covers duplication and missed utility reuse
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.category`

### score
- type: `int 0..100`
- default: 0
- required: false
- semantics: confidence used by the flow to split mandatory findings at 80
- verify: json_path(path="$.findings", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewFinding.score`
