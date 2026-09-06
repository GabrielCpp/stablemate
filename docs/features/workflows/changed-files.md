---
type: format
slug: changed-files
title: Coder changed files
---
# Coder changed files

- file: none — in-memory changed-path result
- config: `ChangedFiles` conversation reseed value
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ChangedFiles`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### paths
- type: `list[str]`
- default: empty list
- required: false
- semantics: sorted unique modified, staged, untracked, or story-commit paths
- verify: json_path(path="$.paths", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ChangedFiles.paths`
