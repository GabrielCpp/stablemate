---
agent: agent
---

# Repair QA OKF Context Grounding

`ostler qa context` or `context-validate` found blocking mapping/health problems before
QA planning.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- Diagnostics: `{{ workhorse_var('context_notes') }}`

Read `qa-okf-context.json` when present and repair only deterministic implementation
grounding: missing/stale `code:` or `tests:` references, unowned changed production
units, or broken as-built links. Use exact `path::qualified-symbol` references and keep
all repeated grounding bullets. Run `ostler fmt` and `ostler doctor` for docs you touch.

Never weaken or rewrite author-owned normative behavior, invariants, journey completion,
persistence, event, consistency, concurrency, or idempotency contracts to match code. If
the implementation contradicts the contract, leave it visible and report a human/product
block. Do not write a QA plan, run QA, or edit runner evidence.

## Commit Identity

Every commit subject ends with `[{{ workhorse_var('story_id') }}]`, after its description.
Every commit also carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
