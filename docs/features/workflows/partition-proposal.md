---
type: format
slug: partition-proposal
title: Survey partition proposal reply
---
# Survey partition proposal reply

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`
- detail: [author surveyor subflow](concepts/author-surveyor-subflow.md)

The partitioner's structured response. A complete proposal can be validated; a blocked one
routes to diagnosis or the operator.

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: partition outcome: `complete` or `blocked`
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`

### notes
- type: string
- default: empty string
- required: false
- semantics: partition explanation or blocking information
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`
