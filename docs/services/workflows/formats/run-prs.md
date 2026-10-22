---
type: format
slug: run-prs
title: Run pull requests result
---
# Run pull requests result

- file: none — an in-memory aggregate of the run's pull-request operations
- config: none — its values are produced while the docs repository and code repositories are processed
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::RunPrs` @b53b8f97caa4
- detail: [coder main PR boundary](../concepts/coder-main-pr-boundary.md)

The result aggregates every repository the run branch changed: one pull request per repository,
opened or found already open, and left open for a reviewer to merge.

## Fields

### status

- type: `Literal["opened", "skipped"]`
- default: `skipped`
- required: false
- semantics: `opened` means at least one repository has an open pull request for the run branch
- semantics: `skipped` means no repository produced or exposed a pull request
- verify: json_path(path="$.status", equals="skipped")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::RunPrs.status` @b53b8f97caa4

### pr_urls

- type: `list[str]`
- default: empty list
- required: false
- semantics: every pull-request URL for the run branch, whether opened during this run or already open
- verify: count(subject="RunPrs.pr_urls entries", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::RunPrs.pr_urls` @b53b8f97caa4
