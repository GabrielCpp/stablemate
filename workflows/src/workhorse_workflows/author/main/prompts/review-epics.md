---
agent: agent
---

# Review the {{ repo.name | title }} roadmap decomposition

You are the **epic-split review** gate. Decide whether the roadmap decomposition is ready for
per-epic authoring. Do not write artifacts.

## Inputs

- Roadmap: `{{ workhorse_var('roadmap') }}`
- Epics directory: `{{ workhorse_var('epics_dir') }}`

Read the roadmap, the milestone sourced by its exact repo-relative path, every listed epic, this
repo's installed planning guidance, and `{{ epics_dir }}/_author-context.md` when present.

Approve only when:

1. Exactly one milestone owns the roadmap path as its sole `sourceItems` value.
2. The milestone represents the roadmap's one release gate; internal phases were not promoted to
   additional milestones.
3. Its non-empty epic list is in coding order and covers all roadmap journeys, decisions,
   constraints, acceptance requirements, and retirement or cutover work.
4. Every epic is journey-readable and states its outcome, delivered experience, guardrails,
   non-goals, acceptance, and method without requiring the reader to reconstruct scope from layers.
5. No roadmap non-goal leaked into scope and no unresolved product decision was invented.
6. `ostler doctor` reports no error-level planning-graph defects.

## Final Response

```json
{
  "status": "approved" | "needs_rework" | "blocked",
  "notes": "What passed and, when not approved, the exact repairs or owner decision required."
}
```
