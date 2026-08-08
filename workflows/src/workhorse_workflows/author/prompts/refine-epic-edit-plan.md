---
agent: agent
---

# Refine an invalid epic edit plan

Plan only. Do not edit files. Return a complete replacement plan, not a patch or an assurance.

## Binding intent

{{ workhorse_var('intent') }}

## Baseline

{{ workhorse_var('snapshot') }}

## Rejected plan

{{ workhorse_var('prior_plan') }}

## Findings that must be fixed

{{ workhorse_var('validation_findings') }}

Resolve every coded finding without weakening the requested add/remove outcome. Preserve unaffected
stories, make every active seed covered, keep dependencies inside the resulting epic and acyclic,
and set `delete_epic` exactly when the resulting seed and story sets are both empty.

Return exactly one complete replacement plan:

```json
{
  "status": "complete" | "blocked",
  "epic": "existing epic name",
  "delete_epic": false,
  "summary": "resulting epic boundary",
  "journey_changes": ["specific journey change"],
  "seed_changes": [],
  "story_changes": [],
  "affected_stories": ["story-slug"],
  "notes": "blocking question or concise rationale"
}
```
