---
type: format
slug: author-config
title: Author workflow configuration
---
# Author workflow configuration

The resolved author paths and layer hints passed from setup to the story-split flow. Paths other
than `repo_root` are repository-relative.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author story-split subflow](concepts/story-split-subflow.md)

## Fields

### repo_root
- type: string path
- default: empty string
- required: true
- semantics: absolute repository root used for graph and artifact operations
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`

### backlog_path
- type: repository-relative string path
- default: empty string
- required: true
- semantics: configured backlog path
- verify: json_path(path="$.backlog_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`

### roadmap_path
- type: repository-relative string path
- default: empty string
- required: true
- semantics: approved roadmap path when the selected mode resolves one
- verify: json_path(path="$.roadmap_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`

### epics_dir
- type: repository-relative string path
- default: empty string
- required: true
- semantics: configured epic directory used to resolve the selected epic
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`

### features_dir
- type: string path
- default: empty string
- required: true
- semantics: configured feature-book directory exposed to author prompts
- verify: json_path(path="$.features_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`

### layers
- type: list of strings
- default: empty list
- required: true
- semantics: best-effort local-instruction skill paths used as prompt layer hints
- verify: json_path(path="$.layers", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
