---
type: format
slug: partition-check
title: Survey partition check
---
# Survey partition check

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The deterministic validation outcome for the finding partition.

## Fields

### partition_ok
- type: boolean
- default: false
- required: false
- semantics: whether the partition covers every assessed unit without invented work
- verify: json_path(path="$.partition_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck`
- detail: [partition check field roles](concepts/partition-check-field-roles.md)

### partition_errors
- type: string
- default: empty string
- required: false
- semantics: diagnostic partition validation errors
- verify: json_path(path="$.partition_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck`
- detail: [partition check field roles](concepts/partition-check-field-roles.md)
