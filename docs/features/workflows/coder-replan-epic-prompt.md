---
type: format
slug: coder-replan-epic-prompt
title: Coder epic replan prompt
---
# Coder epic replan prompt

- file: `workflows/src/workhorse_workflows/coder/main/prompts/replan-epic.md`
- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder.replan`
- detail: [coder main flow](flows/coder-main.md)
- detail: [coder prompt role resolution](concepts/coder-prompt-role-resolution.md)
- detail: [coder rendered schema contracts](concepts/coder-render-schema-contracts.md)

This envelope receives an authoritative epic-scoped operator answer after a story block. It directs
the turn to reread the epic, its stories, and relevant source, re-ground the planning graph without
discarding completed work, and return the typed replan result as the final JSON document.

## Fields

### story_path
- type: string path
- required: true
- semantics: triggering story whose block caused the epic replan
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: story specification directory containing the planning artifacts
- verify: json_path(path="$.spec_dir", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic whose premise, stories, and queue position may be re-grounded when the queue identity is available
- verify: json_path(path="$.epic", matches=".*")

### operator_context
- type: string
- required: true
- semantics: authoritative operator answer that must not be second-guessed or re-raised
- verify: json_path(path="$.operator_context", matches=".+")

### story_slug
- type: string
- required: true
- semantics: triggering story slug used to identify the affected story
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: triggering story identity used for the commit trailer
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract for the `ReplanResult` reply
- verify: json_path(path="$.result_schema", matches=".+")
