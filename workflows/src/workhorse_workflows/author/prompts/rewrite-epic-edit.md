---
agent: agent
---

# Rewrite epic prose after an approved graph edit

Update only the human-authored prose in `{{ workhorse_var('epic_dir') }}/epic.md`. Ostler already
applied the approved seed and story graph. Do not edit the `## Seeds` or `## Stories` sections.

## Binding intent

{{ workhorse_var('intent') }}

## Approved plan

{{ workhorse_var('plan') }}

## Baseline before the edit

{{ workhorse_var('snapshot') }}

## Static findings from the previous prose pass

{{ workhorse_var('validation_findings') }}

The body before `## Seeds` must contain non-empty `## User Outcome`, `## User Journeys`,
`## Delivered Experience`, `## Guardrails`, `## Non-Goals`, `## Acceptance`, and `## Method`.
Under `## User Journeys`, write one `###` subsection per applicable journey. Each journey names its
actor, entry point, ordered observable steps, outcome, required states, and exact segment delivered
by this epic. The revised prose must describe the resulting product, not this edit as a changelog.

Return:

```json
{"status": "complete" | "blocked", "notes": "what changed or the blocking question"}
```
