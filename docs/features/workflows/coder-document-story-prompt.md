---
type: format
slug: coder-document-story-prompt
title: Coder document-story prompt
---
# Coder document-story prompt

- file: `workflows/src/workhorse_workflows/coder/docs/prompts/document-story.md`
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs.document`
- detail: [coder documentation flow](flows/coder-docs.md)
- detail: [coder documentation schemas](concepts/coder-docs-schemas.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_outside_the_docs_worktree_take_the_semantic_route`

This prompt directs the first Docs-subflow agent turn to merge one completed story into the
current as-built OKF graph. It supplies the story and epic context, the classified documentation
context, the initial changed-reference grounding worklist, and any prior gate or review notes.
The turn must return a `DocumentationResult`; the flow uses its status and authored node ids
before running the grounding gate.

## Fields

### story_path
- type: string path
- required: true
- semantics: resolved story document whose implementation delta is being folded into the OKF book
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: story specification directory containing implementation and review artifacts
- verify: json_path(path="$.spec_dir", matches=".+")

### story_slug
- type: string
- required: true
- semantics: short story identity used to scope the documentation pass
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier used in the required commit footer, falling back to the story slug
- verify: json_path(path="$.story_id", matches=".+")

### epic
- type: string
- default: empty string
- required: false
- semantics: optional epic identifier retained for the commit footer
- verify: json_path(path="$.epic", matches=".*")

### docs_path
- type: string path
- required: true
- semantics: documentation repository root containing the story and OKF graph
- verify: json_path(path="$.docs_path", matches=".+")

### features_root
- type: string path
- required: true
- semantics: resolved OKF features directory where service nodes are stored
- verify: json_path(path="$.features_root", matches=".+")

### epic_path
- type: string path
- required: true
- semantics: parent epic document whose user journeys constrain the documentation update
- verify: json_path(path="$.epic_path", matches=".+")

### plan_services
- type: string markdown
- required: true
- semantics: implementation-plan service summary used to scope the source repositories
- verify: json_path(path="$.plan_services", matches=".*")

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
- semantics: deterministic grounding-gate notes from an earlier pass
- verify: json_path(path="$.gate_notes", matches=".*")

### review_notes
- type: string
- default: empty string
- required: false
- semantics: semantic review notes from an earlier pass
- verify: json_path(path="$.review_notes", matches=".*")

### obligations
- type: list[string path]
- default: empty list
- required: false
- semantics: changed production references not yet owned by an OKF code bullet
- verify: json_path(path="$.obligations", matches=".*")

### result_schema
- type: string JSON schema
- required: true
- semantics: rendered top-level JSON contract for the `DocumentationResult` reply
- verify: json_path(path="$.result_schema", matches=".+")
