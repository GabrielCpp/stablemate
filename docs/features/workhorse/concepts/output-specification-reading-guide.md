---
type: concept
slug: output-specification-reading-guide
title: Output specification reading guide
---
# Output specification reading guide

The source defines one `OutputSpec`, not competing implementations: `key` names the value to
extract, and `required` defaults to `true` while allowing a genuinely inapplicable value to be
absent when set to `false`. No source-level ranking or deprecation exists among the concepts that
document this model; they are complementary views of the same contract.

Read [Agent node specification](agent-node-spec.md) for the enclosing `AgentNode`, the ordered
`outputs` declarations, and extraction context. Read [Output specification fields](output-specification-fields.md)
for the `key` and `required` member contract. Read [Output specification documentation](output-specification-documentation.md)
for the model-wide explanation, and [Output specification documentation scope](output-specification-documentation-scope.md)
for the boundary among those views.

- rule: choose the concept by the question being answered; no concept supersedes another because all document complementary views of the single `OutputSpec` model
