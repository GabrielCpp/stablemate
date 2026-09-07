---
type: concept
slug: output-specification-documentation-scope
title: Output specification documentation scope
---
# Output specification documentation scope

`OutputSpec` is one model, not a set of alternative implementations. The source requires its
`key` and defaults `required` to `true`; `required: false` relaxes only the presence check when a
declared value is genuinely inapplicable. The declaration remains identifiable for extraction and
reframing in either case.

Read [Agent node specification](agent-node-spec.md) when deciding where the ordered `outputs`
declarations belong and how extraction uses them. Read [Output specification fields](output-specification-fields.md)
when selecting `key` and whether a valid response permits its absence. Read [Output specification
documentation](output-specification-documentation.md) for the model-wide explanation that joins
those contexts. These concepts have complementary scopes; none is a replacement for another.

- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- rule: use the agent-node concept for declaration placement and extraction context, the output-fields concept for `key` and `required`, and the output-specification documentation concept for the model-wide contract
- detail: [Output specification reading guide](output-specification-reading-guide.md)
