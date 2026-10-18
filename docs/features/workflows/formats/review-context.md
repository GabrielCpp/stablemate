---
type: format
slug: review-context
title: Coder review context
---
# Coder review context

- file: none — in-memory review setup value
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewContext` @818036e1a230
- detail: [coder review schema contracts](../concepts/coder-review-schema-contracts.md)
- detail: [coder review shared nodes](../concepts/coder-review-shared-review.md)

The review context identifies the documentation repository used as the judging working directory
and the code repositories granted to the review turns. An explicit repository supplies the whole
affected set when no plan context is available.

## Fields

### docs_repo_path
- type: `str`
- default: empty string
- required: false
- semantics: filesystem path of the documentation repository and judging working directory
- verify: json_path(path="$.docs_repo_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewContext.docs_repo_path` @818036e1a230

### affected_repo_paths
- type: `list[str]`
- default: empty list
- required: false
- semantics: filesystem paths of code repositories available to the review
- verify: json_path(path="$.affected_repo_paths", matches="^\[.*\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewContext.affected_repo_paths` @818036e1a230
