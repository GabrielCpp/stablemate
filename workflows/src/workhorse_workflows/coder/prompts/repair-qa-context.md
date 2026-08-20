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

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `docs`: this commit writes specification, not product code, and must not
   release a version of anything. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

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
