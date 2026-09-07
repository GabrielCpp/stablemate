---
type: concept
slug: output-specification-fields
title: Output specification fields
---
# Output specification fields

An `OutputSpec` is one declaration of a value to extract from an agent response. Its `key` and
`required` members are complementary, not alternative implementations: every declaration names
the requested value with `key`, then `required` controls whether that declared value may be
inapplicable in a particular response.

`key` has no default, so every output declaration must identify the requested value. `required`
defaults to `true`; set it to `false` only when the value can genuinely be inapplicable for one
branch of an otherwise valid answer. Optional values remain declared so extraction can locate the
response object and report them during a reframe. There is no ranking between these nodes: an
output declaration uses the model and its key together, adding the optionality setting only when
the response contract permits absence.

- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- rule: declare every requested output with `key`; leave `required` true unless the value is genuinely inapplicable for a valid response
- detail: [Output specification reading guide](output-specification-reading-guide.md)
- detail: [Output specification documentation scope](output-specification-documentation-scope.md)
- detail: [Output specification documentation](output-specification-documentation.md)
