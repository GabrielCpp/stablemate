---
agent: agent
---

# Rework the {{ repo.name | title }} epic split

The epic-split review returned changes. Apply them, then return control to the reviewer.

## Inputs (authoritative)

- Backlog file: `{{ workhorse_var('backlog') }}`
- Epics directory: `{{ workhorse_var('epics_dir') }}`
- Review notes to address: `{{ workhorse_var('review_notes') }}`

## Required reading

- The review notes above and `{{ epics_dir }}/_author-context.md` when present (operator answers).
- The backlog, linked source plans, milestone and epic docs in the source checkout, and existing
  target milestone and `epic.md` files.
- This repo's planning method and artifact grammar:
  {{ find_by_tags("planning") | default("(none installed — follow the structure the existing epics establish)", true) }}.

## Task

Address every point in the review notes and preserve the source plan's release milestone, including
its filename, title, epic membership, and order. A fresh target milestone keeps its generated Ostler
id rather than copying the source graph's id. Ensure every eligible full backlog id is owned by
exactly one milestone `sourceItems`; update an active reused milestone with
`ostler milestone set-source-items`, and never reopen a done milestone. Fix
milestone membership and order in milestone files, split or merge overlapping epics, and add all
applicable actor journeys directly to each epic. Complete the required user outcome, journeys, delivered
experience, guardrails, non-goals, acceptance, and method sections. Remove backlog-id scope tables
from the human-facing narrative. Do not write or reorder the legacy todo index.

## Final response (REQUIRED, exact shape)

```json
{
  "status": "complete" | "blocked",
  "notes": "What you changed, or the remaining blocking question."
}
```
