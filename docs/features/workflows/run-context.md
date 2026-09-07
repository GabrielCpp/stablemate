---
type: format
slug: run-context
title: Author run context
---
# Author run context

The checkpointed author context is the resolved path set restored by `setup()` on resume. It has
the same fields and defaults as [author workflow configuration](author-config.md), but names the
state value carried by the run rather than the loader result.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### repo_root
- type: string path
- default: empty string
- required: false
- semantics: absolute repository root resolved for the run
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)

### backlog_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured backlog path restored in the run context
- verify: json_path(path="$.backlog_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)

### roadmap_path
- type: repository-relative string path
- default: empty string
- required: false
- semantics: approved roadmap path restored for epic authoring
- verify: json_path(path="$.roadmap_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)

### epics_dir
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured epic directory restored for path resolution
- verify: json_path(path="$.epics_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)

### features_dir
- type: repository-relative string path
- default: empty string
- required: false
- semantics: configured feature-book directory restored as read-only grounding
- verify: json_path(path="$.features_dir", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)

### layers
- type: list of strings
- default: empty list
- required: false
- semantics: local-instruction skill paths restored as prompt layer hints
- verify: count(subject="$.layers", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- detail: [run context field roles](concepts/run-context-field-roles.md)
