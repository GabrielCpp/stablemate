---
agent: agent
---

# Decompose the {{ repo.name | title }} roadmap into one milestone

You are the **epic-split** stage of the author workflow. Turn one approved roadmap into exactly
one milestone containing coding-ordered epics. Do not write stories yet.

## Inputs

- Roadmap: `{{ workhorse_var('roadmap') }}`
- Epics directory: `{{ workhorse_var('epics_dir') }}`

## Required Reading

- The roadmap above. Its outcome, release boundary, journeys, decisions, constraints,
  acceptance, and non-goals are authoritative.
- This repo's planning method and artifact grammar:
  {{ find_by_tags("planning") | default("(none installed — decompose research-first and dependency-ordered)", true) }}.
- Existing milestones and epics, to avoid duplicate artifacts.
- `{{ epics_dir }}/_author-context.md` when present.

## Contract

1. Create or reuse exactly one active milestone for this roadmap. Internal phases, layers,
   migrations, and rollout steps remain ordered epics inside it; they are not milestones.
2. Set that milestone's `sourceItems` to exactly `{{ workhorse_var('roadmap') }}`. The roadmap
   path is the source identity; do not invent ids for headings or copy roadmap sections into a
   backlog.
3. Give the milestone one positive, ordered epic list. Each epic groups coherent user journeys
   and delivers or materially advances an observable slice of the roadmap outcome.
4. Preserve every locked architecture decision, constraint, acceptance requirement, and non-goal.
   Surface a genuinely unresolved product decision as `blocked`; do not choose for the owner.
5. Create missing milestones and epics with Ostler so it allocates their ids. Do not write or
   reorder the legacy todo index.

This stage may re-run. Reuse the milestone already sourced by this roadmap and refine missing
artifacts; never create a second milestone for the same roadmap or clobber authored epic content.

Each epic skeleton must contain `## User Outcome`, `## User Journeys`, `## Delivered Experience`,
`## Guardrails`, `## Non-Goals`, `## Acceptance`, `## Method`, `## Seeds`, and `## Stories`.

## Final Response

```json
{
  "status": "complete" | "blocked",
  "notes": "The one milestone and ordered epics created or updated, or the blocking question."
}
```
