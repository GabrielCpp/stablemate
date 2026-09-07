---
type: concept
slug: output-specification-documentation
title: Output specification documentation
---
# Output specification documentation

`workhorse/workhorse/runner/spec.py::OutputSpec` has one output-declaration model, not two
alternative implementations. Every declaration supplies `key`, while `required` defaults to
`true` and only relaxes the presence check for a value that is genuinely inapplicable in a valid
response. Optional outputs remain declared so the response object can still be found and named
during a reframe.

Use [Agent node specification](agent-node-spec.md) to understand where an `OutputSpec` is
declared in an agent node and how the ordered `outputs` list controls extraction. Use [Output
specification fields](output-specification-fields.md) to choose the `key` and `required` values
for that declaration. Neither concept supersedes the other: they document the enclosing node and
the same model's field contract at different levels.

- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- rule: read the agent-node concept for `outputs` placement and extraction context; read the output-fields concept to declare `key` and use `required: false` only for genuinely inapplicable values
- detail: [Output specification reading guide](output-specification-reading-guide.md)
- detail: [Output specification documentation scope](output-specification-documentation-scope.md)
