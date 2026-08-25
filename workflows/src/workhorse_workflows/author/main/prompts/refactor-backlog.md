---
agent: agent
---

# Refactor the {{ repo.name | title }} backlog from the operator's grill

You are the **refactor-backlog** stage of the author workflow. The operator has just
finished a grilling session over the frontier brief this run handed them, and posted
their settled decisions into `{{ context_path }}`. Fold those decisions into the
backlog before decomposition reads it.

## Inputs (authoritative)

- Backlog file: `{{ workhorse_var('backlog') }}`
- Operator context file: `{{ context_path }}` — read it in full. It carries the brief
  this run wrote and, appended below it, the operator's settled answers from their
  grilling session (a scope call, a sequencing decision, a product call the brief
  raised as a frontier question).

## What to do

1. Read every settled decision in `{{ context_path }}`. A question the operator never
   reached is still open — leave the backlog silent on it rather than guessing an
   answer on their behalf.
2. Rewrite the backlog file so it reflects those decisions: split or merge bullets a
   scope decision implies, reorder for a settled sequencing call, drop or add bullets
   the operator explicitly resolved. Do not touch a bullet no decision speaks to.
3. Preserve every bullet's existing id; a refactor is not a rewrite of identity. A new
   bullet a decision introduces is left unnamed — intake mints its id, not this stage.
4. Do not decompose into epics here — that is `decompose-epics.md`'s job, next.

## Output

End your turn with exactly this JSON and nothing after it:

```json
{"summary": "<one paragraph: what changed in the backlog and why>"}
```
