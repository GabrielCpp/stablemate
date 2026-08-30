---
agent: agent
---

# Write the epic: `{{ workhorse_var('epic') }}`

Change only the planning artifacts named by this task. Leave them uncommitted: do not install
dependencies, run repository-wide checks, stage, commit, push, or alter branches/remotes; Author
validates and delivers after all authoring turns finish.

Research this epic's share of the roadmap, author its narrative, and record durable seeds in its
canonical `## Seeds` section. Do not write stories yet.

## Inputs

- Epic: `{{ workhorse_var('epic') }}`
- Epic directory: `{{ workhorse_var('epic_dir') }}`
- Source roadmap: `{{ workhorse_var('roadmap') }}`

Read the roadmap, this epic and its neighboring epics in milestone order, installed planning and
artifact guidance, `{{ epic_dir }}/context.md` when present, and the read-only OKF book under
`{{ workhorse_var('features_dir') }}` when configured. Existing docs and OKF are the discovery
boundary; do not inspect the running app or source code to invent surfaces, and never write the
feature book.

Author `{{ epic_dir }}/epic.md` with `## User Outcome`, `## User Journeys`,
`## Delivered Experience`, `## Guardrails`, `## Non-Goals`, `## Acceptance`, and `## Method`
before the graph-owned `## Seeds` and `## Stories` sections. Keep the epic's journey segment
vertical and independently observable while preserving every roadmap decision and constraint that
applies to it.

Record each distinct in-scope behavior as a researched `### <stable-seed-id>` block under
`## Seeds`, following the installed artifact grammar. Write or refine the complete seed set in one
edit; do not launch a separate `ostler seed add` process per seed, because each process reloads the
whole book. Seeds derive from this epic's roadmap journey segment, not independently pruneable
roadmap headings, so omit `sourceBullet`. Populate documented surfaces, backing services,
prerequisites, layers, and services from evidence. Tag every seed with `frontend`, `backend`, and/or
`infra` as applicable. On every frontend seed, add `design: required` for a new or materially
changed visual experience, or `design: preserve` when the existing visual contract remains intact;
these fields deterministically decide whether a later story receives a design turn. Every epic
obligation must map to at least one seed, and every seed id must be stable for story coverage.

If the existing docs cannot establish a required fact, record the uncertainty and return `blocked`
when an owner decision is required. On re-run, refine existing seeds instead of discarding them.

## Final Response

```json
{
  "status": "complete" | "blocked",
  "notes": "Items recorded, or the blocking question for the operator."
}
```
