---
type: concept
slug: author-resolve-operator-field-roles
title: Author resolve-operator field roles
---
# Author resolve-operator field roles

The resolve-operator call has one input bundle and one diagnostic report shape, not alternative
field implementations. `context_path`, `epic_dir`, `block_stage`, and `block_notes` are supplied
together to the resolver. `decision`, `notes`, and `tried` describe its report: `decision` remains
in the shape for the former auto-resolve contract, while the resolver's live report uses `notes`
and `tried` before the flow parks at the operator gate.

No ranking exists among these fields. A caller supplies each input field for its named purpose and
the diagnostic result carries each report field for its named purpose; none is a substitute for
another. The prompt requires the diagnostic investigator to escalate rather than make the
operator's decision, so `decision` does not select a different resolver outcome.

- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution`
- code: `workflows/src/workhorse_workflows/author/shared/prompts/resolve-operator.md`
- rule: supply the four named resolver inputs together, then interpret each diagnostic report field by its named role; do not substitute or rank fields
