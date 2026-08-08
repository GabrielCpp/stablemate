---
agent: agent
---

# Review an epic edit plan

You are the semantic review gate. Do not edit files. Static graph checks have passed; judge whether
the proposed scope and story partition actually satisfy the operator intent and remain buildable.

## Intent

{{ workhorse_var('intent') }}

## Baseline

{{ workhorse_var('snapshot') }}

## Statically valid plan

{{ workhorse_var('plan') }}

Check actor outcomes, entry points, ordered journey steps, required states, story-sized deliverables,
real dependency order, and whether affected stories are complete. Reject a mechanical add that leaves
the epic journey describing the old product. Reject a removal that hides remaining scope or leaves a
dependent journey impossible.

Return:

```json
{
  "status": "approved" | "needs_rework" | "blocked",
  "notes": "specific semantic changes or blocking question"
}
```
