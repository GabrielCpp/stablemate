---
type: format
slug: author-resolve-integrity-prompt
title: Author resolve-integrity prompt
---
# Author resolve-integrity prompt

The finalize flow invokes this diagnostic template when the graph-integrity gate (`ostler doctor`) detects referential-integrity breaks. It asks the high-power agent to reconcile each break — dangling references, orphaned entities, or cross-epic dependencies — by using `ostler edit` to relink or rename within the source of truth, or escalate when the correct target does not exist. The agent has an unbounded timeout so diagnostic responses are not cut off. The expected response is an `OperatorResolution` carrying the decision (`answered` or `escalated`), a one-line plain-language statement of what was reconciled, and a list of investigations the agent ruled out or completed.

- file: `workflows/src/workhorse_workflows/author/finalize/prompts/resolve-integrity.md`
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`
- detail: [author finalize subflow](concepts/author-finalize-subflow.md)

## Fields

### context_path
- type: `str`
- required: true
- semantics: the operator context file the agent must preserve and append its answers to
- verify: json_path(path="$.context_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

### epics_dir
- type: `str`
- required: true
- semantics: the canonical epics directory whose documents the agent inspects and edits
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

### integrity_errors
- type: `str`
- required: true
- semantics: the ostler doctor error-level findings the agent reconciles by fixing references or raising unsolvable breaks
- verify: json_path(path="$.integrity_errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

### decision
- type: `str`
- required: true
- semantics: the resolution outcome, which must be `answered` when the agent reconciles all breaks or `escalated` when a correct target does not exist
- verify: json_path(path="$.decision", matches="^(answered|escalated)$")
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

### notes
- type: `str`
- required: true
- semantics: the one-line plain-language statement of what was reconciled or what remains unsolvable
- verify: json_path(path="$.notes", matches=".+")
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

### tried
- type: `list[str]`
- required: true
- semantics: concrete investigations and dead ends the agent ruled out, supplied to avoid re-running the same diagnostic work on a retry
- verify: json_path(path="$.tried", matches=".*")
- detail: [author resolve-integrity field roles](concepts/author-resolve-integrity-field-roles.md)

