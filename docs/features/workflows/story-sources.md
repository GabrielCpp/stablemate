---
type: format
slug: story-sources
title: Coder story sources
---
# Coder story sources

- file: none — in-memory multi-repository provenance result
- config: `StorySources` source resolution result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySources` @b6e19c205b4f
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### status
- type: literal `valid` or `invalid`
- default: `valid`
- required: false
- semantics: whether story source provenance was resolved
- verify: json_path(path="$.status", matches="valid|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySources.status` @b6e19c205b4f

### sources
- type: `tuple[StorySource, ...]`
- default: empty tuple
- required: false
- semantics: deduplicated source roots with repository provenance
- verify: json_path(path="$.sources", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySources.sources` @b6e19c205b4f

### errors
- type: `tuple[str, ...]`
- default: empty tuple
- required: false
- semantics: source-resolution failures
- verify: json_path(path="$.errors", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::StorySources.errors` @b6e19c205b4f
