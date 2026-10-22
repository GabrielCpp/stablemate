---
type: concept
slug: operator-resolution-documentation-context
title: Operator resolution documentation context
---
# Operator resolution documentation context

`OperatorResolution` is one diagnostic report model, not a family of interchangeable
implementations. Its source declares `decision` only to preserve the former auto-resolve reply
shape; the live diagnostic fields are `notes` and `tried`, and the resolver always returns to
`Await` for an operator decision.

Use [Author resolve-operator field roles](author-resolve-operator-field-roles.md) when reading
the complete `EpicAuthor.resolve_epic` invocation, including its four resolver inputs and returned
report. Use [Surveyor operator resolution field roles](surveyor-operator-resolution-field-roles.md)
when interpreting the report itself. [Author operator resolution contexts](author-operator-resolution-contexts.md)
summarizes the same distinction. Neither scope supersedes another: each documents the one model
for a different reader need.

- rule: use the Author concept for resolver invocation and report-field roles together; use the Surveyor concept for report-field interpretation alone; neither scope is preferred over the other
