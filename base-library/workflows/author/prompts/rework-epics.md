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
- The backlog, the epics queue (`ostler todo list`, backed by `{{ epics_dir }}/index.md`), and the
  existing `epic.md` files.
- `{{ instruction_ref('write-epics-and-stories') }}`, `{{ instruction_ref('story-docs') }}`.

## Task

Address every point in the review notes (and any operator answer): fix coverage gaps, re-order
epics into correct coding order (`ostler todo reorder <slug...>`), split/merge overlapping epics
(`ostler create epic` / `ostler delete epic`, then `ostler todo add`/`prune`), and complete any
`epic.md` that is missing its goal / source-of-truth / scope / acceptance. Preserve epics that were
already correct — change only what the notes call out.

## Final response (REQUIRED, exact shape)

```json
{
  "decompose_result": {
    "status": "complete" | "blocked",
    "notes": "What you changed, or the remaining blocking question."
  }
}
```
