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
grounding: missing/stale `code:` or `verify:` references, unowned changed production
units, or broken as-built links. Use exact `path::qualified-symbol` references and keep
all repeated grounding bullets. Run `ostler fmt` and `ostler doctor` for docs you touch.

Never weaken or rewrite author-owned normative behavior, invariants, journey completion,
persistence, event, consistency, concurrency, or idempotency contracts to match code. If
the implementation contradicts the contract, leave it visible and report a human/product
block. Do not write a QA plan, run QA, or edit runner evidence.

Return JSON only:

```json
{
  "qa_context_repair": {
    "status": "repaired",
    "notes": "Updated exact code/verify grounding for the reported mappings."
  },
  "qa_result": {
    "status": "invalid",
    "notes": "Context is being regenerated after grounding repair."
  }
}
```

Use `qa_context_repair.status=blocked` and `qa_result.status=blocked` only when repair
requires an author/product decision or unavailable source repository.
