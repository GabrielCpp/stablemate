---
type: format
slug: coder-review-story-documentation-prompt
title: Coder review-story-documentation prompt
---
# Coder review-story-documentation prompt

- file: `workflows/src/workhorse_workflows/coder/docs/prompts/review-story-documentation.md`
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs.review`
- detail: [coder documentation flow](flows/coder-docs.md)
- detail: [coder documentation schemas](concepts/coder-docs-schemas.md)
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_reviewer_is_handed_the_unnarrowed_story_delta`

This prompt directs the independent review turn after the deterministic grounding gate passes.
The reviewer compares the frozen story implementation and current OKF book within the original
story scope, then returns a `DocumentationReview` with an approval, structured revision findings,
or a block. The original obligations remain available even after the author closes some items.

## Fields

### story_path
- type: string path
- required: true
- semantics: story document defining the implementation scope under review
- verify: json_path(path="$.story_path", matches=".+")

### spec_dir
- type: string path
- required: true
- semantics: story specification directory containing the implementation evidence
- verify: json_path(path="$.spec_dir", matches=".+")

### docs_path
- type: string path
- required: true
- semantics: documentation repository root containing the current OKF book
- verify: json_path(path="$.docs_path", matches=".+")

### features_root
- type: string path
- required: true
- semantics: resolved OKF features directory being reviewed
- verify: json_path(path="$.features_root", matches=".+")

### epic_path
- type: string path
- required: true
- semantics: parent epic document supplying authoritative user journeys
- verify: json_path(path="$.epic_path", matches=".+")

### author_status
- type: string
- required: true
- semantics: documentation author's terminal decision supplied as review context
- verify: json_path(path="$.author_status", matches="^(documented|not_required|blocked)$")

### author_notes
- type: string
- default: empty string
- required: false
- semantics: author's explanation of the documentation pass
- verify: json_path(path="$.author_notes", matches=".*")

### gate_notes
- type: string
- default: empty string
- required: false
- semantics: deterministic grounding-gate result and any remaining notes
- verify: json_path(path="$.gate_notes", matches=".*")

### review_notes
- type: string
- default: empty string
- required: false
- semantics: previous semantic review notes used to preserve finding identities
- verify: json_path(path="$.review_notes", matches=".*")

### obligations
- type: list[string path]
- default: empty list
- required: false
- semantics: original, unnarrowed changed production references in review scope
- verify: json_path(path="$.obligations", matches=".*")

### result_schema
- type: string JSON schema
- required: true
- semantics: rendered top-level JSON contract for the `DocumentationReview` reply
- verify: json_path(path="$.result_schema", matches=".+")
