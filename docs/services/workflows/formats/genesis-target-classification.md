---
type: format
slug: genesis-target-classification
title: Genesis target classification
---
# Genesis target classification

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification` @597dd3afbe90
- detail: [coder genesis bootstrap](../concepts/coder-genesis-bootstrap.md)

The classification separates repository state from service state before genesis mutates
the target.

## Fields

### ok
- type: boolean
- default: false
- required: false
- semantics: whether the target classification is usable
- verify: json_path(path="$.ok", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.ok` @597dd3afbe90

### target_dir
- type: string
- default: empty string
- required: false
- semantics: resolved target directory
- verify: json_path(path="$.target_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.target_dir` @597dd3afbe90

### target_state
- type: `absent | partial | existing`
- default: absent
- required: false
- semantics: whether the target is missing or empty, has content without configuration, or already has agents.yml
- verify: json_path(path="$.target_state", matches="^(absent|partial|existing)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.target_state` @597dd3afbe90

### service_state
- type: `existing | absent`
- default: absent
- required: false
- semantics: whether the declared service marker already exists
- verify: json_path(path="$.service_state", matches="^(existing|absent)$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.service_state` @597dd3afbe90

### service
- type: string
- default: empty string
- required: false
- semantics: logical service being bootstrapped
- verify: json_path(path="$.service", equals="example service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.service` @597dd3afbe90

### note
- type: string
- default: empty string
- required: false
- semantics: operator-facing classification explanation
- verify: json_path(path="$.note", equals="example note")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::TargetClassification.note` @597dd3afbe90
