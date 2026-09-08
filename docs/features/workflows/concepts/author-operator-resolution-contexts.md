---
type: concept
slug: author-operator-resolution-contexts
title: Author operator resolution contexts
---
# Author operator resolution contexts

`OperatorResolution` is one diagnostic report shape, not two implementations. Its source declares
`decision` only to retain the former auto-resolve shape; the live diagnostic fields are `notes` and
`tried`, and the resolver always returns to `Await` for an operator decision.

Use [Author resolve-operator field roles](author-resolve-operator-field-roles.md) when a reader
needs the complete `EpicAuthor.resolve_epic` call: the four inputs it passes to the resolver and
the report fields returned with that call. Use [Surveyor operator resolution field roles](surveyor-operator-resolution-field-roles.md)
when the reader only needs to interpret the diagnostic report. Neither concept supersedes the
other: they describe the same schema at different scopes.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::OperatorResolution`
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`
- rule: use the Author concept for resolver invocation and report-field roles together; use the Surveyor concept for report-field interpretation alone; neither is preferred over the other
- detail: [operator resolution documentation context](operator-resolution-documentation-context.md)
