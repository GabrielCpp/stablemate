---
type: concept
slug: author-resolve-operator-documentation-selection
title: Author resolve-operator documentation selection
---
# Author resolve-operator documentation selection

`EpicAuthor.resolve_epic` has one resolver invocation. It supplies `context_path`, `epic_dir`,
`block_stage`, and `block_notes` together, discards the diagnostic report returned by the agent,
and always parks the epic at `Await` with the original notes after the invocation.

[Author operator resolution contexts](author-operator-resolution-contexts.md) explains that
single invocation's diagnostic context and report shape. [Author resolve-operator field
roles](author-resolve-operator-field-roles.md) names the purpose of each input and report field.
Neither is an alternative implementation or supersedes the other; choose the context summary for
the whole diagnostic exchange and the field-role reference for an individual value's purpose.

- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- rule: use the context summary for the diagnostic exchange and the field-role reference for an individual input or report value; neither is preferred because both describe the one invocation
- detail: [operator resolution documentation context](operator-resolution-documentation-context.md)
