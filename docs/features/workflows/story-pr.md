---
type: format
slug: story-pr
title: Story pull request result
---
# Story pull request result

- file: none — an in-memory aggregate of story pull-request operations
- config: none — its values are produced while affected repositories are processed
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::StoryPr`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result aggregates all affected code repositories: it reports the strongest outcome in the
order `opened`, `exists`, `skipped`, and retains every PR URL that exists after processing.

## Fields

### story_pr

- type: `Literal["opened", "exists", "skipped"]`
- default: `skipped`
- required: false
- semantics: `opened` means at least one new story PR was created
- semantics: `exists` means no new PR was created but an existing one was found
- semantics: `skipped` means no affected repository produced or exposed a PR
- verify: json_path(path="$.story_pr", equals="skipped")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::StoryPr.story_pr`

### pr_urls

- type: `list[str]`
- default: empty list
- required: false
- semantics: every pull-request URL currently associated with the affected repositories, whether opened during this run or already present
- verify: json_path(path="$.pr_urls", equals=[])
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::StoryPr.pr_urls`
