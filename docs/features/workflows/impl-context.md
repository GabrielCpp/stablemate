---
type: format
slug: impl-context
title: Coder implementation context
---
# Coder implementation context

- file: none — in-memory implementation context
- config: `ImplContext` value handed to implementation and QA planning
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### qa_run_plan
- type: `list[QaRunEntry]`
- default: empty list
- required: false
- semantics: service QA briefs
- verify: json_path(path="$.qa_run_plan", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.qa_run_plan`

### verification_setup
- type: `dict[str, Any]`
- default: empty mapping
- required: false
- semantics: story verification setup copied from the plan
- verify: json_path(path="$.verification_setup", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.verification_setup`

### fixtures
- type: `list[PlanFixture]`
- default: empty list
- required: false
- semantics: named QA fixtures available to the planner
- verify: json_path(path="$.fixtures", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.fixtures`

### shared_packages
- type: `list[str]`
- default: empty list
- required: false
- semantics: shared directories changed by the plan
- verify: json_path(path="$.shared_packages", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.shared_packages`

### dispatch_list
- type: `list[DispatchEntry]`
- default: empty list
- required: false
- semantics: ordered service implementation entries
- verify: json_path(path="$.dispatch_list", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.dispatch_list`

### affected_repos
- type: `list[str]`
- default: empty list
- required: false
- semantics: repositories affected by the story
- verify: json_path(path="$.affected_repos", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.affected_repos`

### affected_repo_paths
- type: `list[str]`
- default: empty list
- required: false
- semantics: affected repository paths including the documentation root when needed
- verify: json_path(path="$.affected_repo_paths", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.affected_repo_paths`

### qa_source_roots
- type: `list[str]`
- default: empty list
- required: false
- semantics: unique source-root paths supplied to QA
- verify: json_path(path="$.qa_source_roots", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.qa_source_roots`

## Methods

### dispatch_count
- sig: `dispatch_count -> int`
- returns: the length of `dispatch_list`
- verify: count(subject="implementation dispatch count", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplContext.dispatch_count`
