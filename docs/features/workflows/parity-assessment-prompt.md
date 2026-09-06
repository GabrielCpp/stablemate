---
type: format
slug: parity-assessment-prompt
title: Parity assessment prompt contract
---
# Parity assessment prompt contract

- file: `workflows/src/workhorse_workflows/author/parity_surveyor/prompts/assess-parity-unit.md`
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.assess`
- detail: [author parity surveyor subflow](concepts/parity-surveyor-subflow.md)
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_the_assessor_is_handed_the_unit_and_both_sides_of_the_compare`

The prompt assesses exactly one frozen legacy surface against the current OKF book. It reads the
baseline surface in full, searches the current graph and author planning artifacts for behavioral
coverage or existing ownership, and writes only the finding record. A covered surface is `clean`
with no findings; an uncovered or materially incomplete surface is `assessed` with one finding,
the `legacy-surface-parity` remediation pattern, an effort enum, and concrete evidence. An
existing owner is recorded without suppressing the assessment; emission performs that suppression.

## Fields

### unit_id
- type: string identifier
- required: true
- semantics: frozen legacy-surface identifier being assessed
- verify: json_path(path="$.unit_id", matches=".+")

### unit_path
- type: string path
- required: true
- semantics: baseline surface document read in full for the assessment
- verify: json_path(path="$.unit_path", matches=".+")

### unit_kind
- type: string
- required: true
- semantics: frozen inventory kind, `legacy-surface`
- verify: json_path(path="$.unit_kind", equals="legacy-surface")

### record_path
- type: string path
- required: true
- semantics: finding-record path the turn must write
- verify: json_path(path="$.record_path", matches=".+")

### baseline_inventory
- type: string path
- required: true
- semantics: baseline JSON inventory used to establish the surface's legacy context
- verify: json_path(path="$.baseline_inventory", matches=".+")

### target_features
- type: string path
- required: true
- semantics: current OKF feature-book root searched for behavioral correspondence
- verify: json_path(path="$.target_features", matches=".+")

### backlog
- type: string path
- required: true
- semantics: existing author backlog searched for ownership of the exact surface
- verify: json_path(path="$.backlog", matches=".+")

### epics_dir
- type: string path
- required: true
- semantics: existing epic directory searched for ownership of the exact surface
- verify: json_path(path="$.epics_dir", matches=".+")

### status
- type: string
- required: true
- semantics: reply outcome, `clean` when behaviorally covered or `assessed` when a gap is recorded
- verify: json_path(path="$.status", matches="^(clean|assessed)$")

### notes
- type: string
- required: true
- semantics: one-line assessment result returned to the workflow state
- verify: json_path(path="$.notes", matches=".+")
