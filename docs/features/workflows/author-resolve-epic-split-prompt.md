---
type: format
slug: author-resolve-epic-split-prompt
title: Author resolve-epic-split prompt
---
# Author resolve-epic-split prompt

The epic-split flow renders this template for its resolution turn, which diagnoses and escalates blocking issues when the split and review cycle cannot converge on an approved skeleton list. It directs an unbounded-timeout agent to investigate why the milestone split has blocked, read any prior operator context if it exists, and append concrete findings and decision options under a `## Findings` section. The agent applies decisions only when grounded in a written record—a docs/decisions/ precedent, an installed skill, or the story spec—and escalates unwritten product or scope calls to the operator. The expected response is a JSON object with `decision` set to `escalated` and a `notes` value describing the decision required.

- file: `workflows/src/workhorse_workflows/author/epic_split/prompts/resolve-epic-split.md`
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [author epic-split subflow](concepts/author-epic-split-subflow.md)
- detail: [operator resolution](operator-resolution.md)
- tests: `workflows/tests/author/epic_split/test_flow.py::test_creates_only_ordered_epic_skeletons_after_review_rework`

## Fields

### roadmap
- type: `str`
- required: true
- semantics: path to the approved roadmap document
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split context](epic-split-context.md)
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

### milestone
- type: `str`
- required: true
- semantics: path to the milestone document where the split has blocked
- verify: json_path(path="$.milestone", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split context](epic-split-context.md)
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

### epics_dir
- type: `str`
- required: true
- semantics: canonical directory path for epic skeletons
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split context](epic-split-context.md)
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

### review_notes
- type: `str`
- default: empty string
- required: false
- semantics: review feedback from prior turns
- verify: json_path(path="$.review_notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

### context_path
- type: `str`
- required: true
- semantics: file path to the operator context document where findings and decisions accumulate
- verify: json_path(path="$.context_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

### block_notes
- type: `str`
- required: true
- semantics: explanation of why the prior review/rework cycle could not converge
- verify: json_path(path="$.block_notes", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- detail: [epic split resolve prompt args](concepts/epic-split-resolve-prompt-args.md)

## Response

### decision
- type: literal `escalated`
- required: true
- consistency: operator-resolution — `EpicSplit.resolve` always returns `Await`, so this response always escalates to the operator
- verify: json_path(path="$.decision", equals="escalated")
- consistency: operator-resolution — an unwritten decision is never this agent's to make
- verify: json_path(path="$.decision", equals="escalated")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
- detail: [operator resolution](operator-resolution.md)

### notes
- type: `str`
- required: true
- semantics: the specific operator decision required, grounded in evidence or escalated as unwritten
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
- detail: [operator resolution](operator-resolution.md)

### tried
- type: `array[str]`
- required: false
- default: empty array
- semantics: list of evidence sources checked before escalating
- verify: json_path(path="$.tried", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::OperatorResolution`
- detail: [operator resolution](operator-resolution.md)

