---
type: format
slug: survey-partition-prompt
title: Survey partition prompt contract
---
# Survey partition prompt contract

- file: `workflows/src/workhorse_workflows/author/surveyor/prompts/partition-findings.md`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)
- tests: `workflows/tests/author/surveyor/test_partition.py::test_a_partition_covering_every_assessed_unit_is_valid`

The partitioner reads every assessed finding record and the frozen inventory, then writes a YAML
partition of remediation clusters. Shared remediation patterns form mechanical checklist stories;
interacting or substantial work forms dedicated clusters. Every assessed unit must appear in at
least one cluster, while clean and blocked units carry no remediation work.

## Fields

### findings_dir
- type: string path
- required: true
- semantics: directory whose assessed finding records are all read before clustering
- verify: json_path(path="$.findings_dir", matches=".+")

### inventory
- type: string path
- required: true
- semantics: frozen unit list used to enforce lossless cluster coverage
- verify: json_path(path="$.inventory", matches=".+")

### rubric
- type: string path
- required: true
- semantics: survey concern used to order and prioritize remediation clusters
- verify: json_path(path="$.rubric", matches=".+")

### context_path
- type: string path
- required: true
- semantics: operator context consulted for a prior partition decision
- verify: json_path(path="$.context_path", matches=".+")

### partition_path
- type: string path
- required: true
- semantics: YAML artifact receiving ordered, lossless clusters
- verify: json_path(path="$.partition_path", matches=".+")

### partition_errors
- type: string
- default: empty string
- required: false
- semantics: deterministic validation errors supplied for partition repair
- verify: json_path(path="$.partition_errors", matches=".*")

### status
- type: string
- default: empty string
- required: false
- semantics: reply outcome, `complete` when a partition was written or `blocked` when clustering needs an operator decision
- verify: json_path(path="$.status", matches=".*")

### notes
- type: string
- default: empty string
- required: false
- semantics: clustering rationale or blocking information
- verify: json_path(path="$.notes", matches=".*")
