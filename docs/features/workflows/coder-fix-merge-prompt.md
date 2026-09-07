---
type: format
slug: coder-fix-merge-prompt
title: Coder merge-fix prompt
---
# Coder merge-fix prompt

- file: `workflows/src/workhorse_workflows/coder/main/prompts/fix-merge.md`
- code: `workflows/src/workhorse_workflows/coder/main/flow.py::Coder.fix_merge`
- detail: [coder main flow](flows/coder-main.md)
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)
- detail: [coder prompt role resolution](concepts/coder-prompt-role-resolution.md)
- detail: [coder rendered schema contracts](concepts/coder-render-schema-contracts.md)

This envelope asks a high-power turn to make an epic branch mergeable into its base. It requires
stale-duplicate diagnosis before content merging, preserves both sides when resolving conflicts,
forbids pushing or merging except for the explicitly permitted stale-branch repair, and returns the
typed merge-fix result as the final JSON document.

## Fields

### ci_epic
- type: string
- required: true
- semantics: epic identity and source branch used for merge repair
- verify: json_path(path="$.ci_epic", matches=".+")

### ci_base
- type: string
- required: true
- semantics: target base branch that the epic branch must merge into
- verify: json_path(path="$.ci_base", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract for the `MergeFixResult` reply
- verify: json_path(path="$.result_schema", matches=".+")
