---
agent: agent
---

# Rework the {{ repo.name | title }} roadmap decomposition

Change only the planning artifacts named by this task. Leave them uncommitted: do not install
dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes; Author
validates and delivers after all authoring turns finish.

Apply every review finding, then return control to the reviewer.

## Inputs

- Roadmap: `{{ workhorse_var('roadmap') }}`
- Epics directory: `{{ workhorse_var('epics_dir') }}`
- Review notes: `{{ workhorse_var('review_notes') }}`

Read the roadmap, review notes, existing milestone and epic files, installed planning guidance,
and `{{ epics_dir }}/_author-context.md` when present.

Restore the one-roadmap-to-one-milestone contract. Exactly one active milestone must list only the
roadmap path in `sourceItems`, and its positive epic list must preserve the roadmap's release gate,
journeys, decisions, constraints, acceptance, and non-goals in coding order. Merge accidental phase
milestones back into that release milestone. Do not invent product decisions, roadmap-section ids,
or a backlog, and do not write the legacy todo index.

## Final Response

```json
{
  "status": "complete" | "blocked",
  "notes": "What changed, or the remaining blocking question."
}
```
