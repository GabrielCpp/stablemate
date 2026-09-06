---
type: format
slug: coder-repair-documentation-prompt
title: Coder repair-documentation prompt
---
# Coder repair-documentation prompt

- file: `workflows/src/workhorse_workflows/coder/docs/prompts/repair-documentation.md`
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs.repair`
- detail: [coder documentation flow](flows/coder-docs.md)
- detail: [coder documentation schemas](concepts/coder-docs-schemas.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_gates_failure_does_not_spend_the_reviewers_budget`

This prompt directs later Docs-subflow turns to repair only the nodes cited by deterministic gate
or semantic review findings. It carries the same story and context needed to inspect the book,
the current outstanding grounding identities, and prior notes; it instructs the turn to preserve
unaffected nodes and to return a `DocumentationResult`. The flow limits the repair turn to its
wall-clock budget and uses the same prompt for grounding and review rework.

## Fields

### story_path
- type: string path
- required: true
- semantics: resolved story document whose documentation findings are being repaired
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: story specification directory containing implementation evidence
- verify: json_path(path="$.spec_dir", matches=".+")

### docs_path
- type: string path
- required: true
- semantics: documentation repository root containing the affected OKF nodes
- verify: json_path(path="$.docs_path", matches=".+")

### features_root
- type: string path
- required: true
- semantics: resolved OKF features directory containing the affected nodes
- verify: json_path(path="$.features_root", matches=".+")

### epic_path
- type: string path
- required: true
- semantics: parent epic document supplying journey and scope context
- verify: json_path(path="$.epic_path", matches=".+")

### context_mode
- type: string
- required: true
- semantics: documentation grounding mode, local or semantic
- verify: json_path(path="$.context_mode", matches="^(local|semantic)$")

### context_notes
- type: string
- default: empty string
- required: false
- semantics: classifier explanation accompanying the grounding mode
- verify: json_path(path="$.context_notes", matches=".*")

### gate_notes
- type: string
- default: empty string
- required: false
- semantics: current deterministic gate findings and repair instructions
- verify: json_path(path="$.gate_notes", matches=".*")

### review_notes
- type: string
- default: empty string
- required: false
- semantics: current semantic review findings and repair instructions
- verify: json_path(path="$.review_notes", matches=".*")

### obligations
- type: list[string path]
- default: empty list
- required: false
- semantics: outstanding changed production references still requiring direct ownership
- verify: json_path(path="$.obligations", matches=".*")

### story_id
- type: string
- required: true
- semantics: story identifier used in the required commit footer
- verify: json_path(path="$.story_id", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: optional epic identifier used in the required commit footer
- verify: json_path(path="$.epic", matches=".*")

### node_timeout_min
- type: string
- required: true
- semantics: displayed wall-clock budget for the repair turn
- verify: json_path(path="$.node_timeout_min", matches=".+")

### result_schema
- type: string JSON schema
- required: true
- semantics: rendered top-level JSON contract for the `DocumentationResult` reply
- verify: json_path(path="$.result_schema", matches=".+")
