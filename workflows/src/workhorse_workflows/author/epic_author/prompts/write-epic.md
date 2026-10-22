---
agent: agent
---

# Write the epic: `{{ workhorse_var('epic') }}`

Change only the planning artifacts named by this task. Leave them uncommitted: do not install
dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes; Author
validates and delivers after all authoring turns finish.

Research this epic's share of the milestone, author its narrative, and record durable seeds in its
canonical `## Seeds` section. Do not write stories yet.

## Inputs

- Epic: `{{ workhorse_var('epic') }}`
- Epic directory: `{{ workhorse_var('epic_dir') }}`
- Source milestone: `{{ workhorse_var('milestone') }}`
{%- if workhorse_var('note') %}

## Answer to your question

{{ workhorse_var('note') }}
{%- endif %}

Read the milestone, its `grills/` records, this epic and its neighboring epics in milestone order, installed planning and
artifact guidance, and the read-only OKF book under
`{{ workhorse_var('services_dir') }}` when configured. Existing docs and OKF are the discovery
boundary; do not inspect the running app or source code to invent surfaces, and never write the
feature book.

Author `{{ epic_dir }}/epic.md` with `## User Outcome`, `## User Journeys`,
`## Delivered Experience`, `## Guardrails`, `## Non-Goals`, `## Acceptance`, and `## Method`
before the graph-owned `## Seeds` and `## Stories` sections. Keep the epic's journey segment
vertical and independently observable while preserving every milestone decision and constraint that
applies to it.

Record each distinct in-scope behavior as a researched `### <stable-seed-id>` block under
`## Seeds`, following the installed artifact grammar. Write or refine the complete seed set in one
edit; do not launch a separate `ostler seed add` process per seed, because each process reloads the
whole book. Seeds derive from this epic's milestone journey segment, not independently pruneable
milestone headings, so omit `sourceBullet`. Populate documented surfaces, backing services,
prerequisites, and services from evidence. A seed's `services:` lists book names, each a directory under
`docs/services/`, and nothing else. The story split derives each story's services from the seeds
it covers, so a seed with no `services:` leaves its story without any. Every epic
obligation must map to at least one seed, and every seed id must be stable for story coverage.

If the existing docs cannot establish a required fact, record the uncertainty and return `blocked`
when an owner decision is required. The product manager answers it, or the operator does, and you are
run again with the answer. On re-run, refine existing seeds instead of discarding them.
{% include "pm/prompts/ledger.md" %}

## Final Response

```json
{
  "status": "complete" | "blocked",
  "notes": "Items recorded, or the blocking question."
}
```
