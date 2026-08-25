---
agent: agent
---

# Review the {{ repo.name | title }} milestone and epic split

You are the **epic-split review** gate. Decide whether the epic decomposition is ready for
per-epic authoring. Do not write epics or stories.

## Inputs (authoritative)

- Backlog file: `{{ workhorse_var('backlog') }}`
- Epics directory: `{{ workhorse_var('epics_dir') }}`

## Required reading

- The backlog file, any source roadmap it links, milestone and epic docs in that source checkout,
  milestone files under the target's `docs/milestones/`, and every target `epic.md` just authored.
- This repo's planning method and artifact grammar — the rules these epics are judged against:
  {{ find_by_tags("planning") | default("(none installed — judge against the backlog and the epics' own stated method)", true) }}.
- `{{ epics_dir }}/_author-context.md` when present — operator answers to earlier questions,
  including repo-location mixups from a prior blocked pass.

If the backlog file or epics directory above don't exist relative to your current working
directory, do not conclude the repo is missing before checking two things: the `_author-context.md`
file just listed (an earlier stage may have already resolved a working-directory mixup — its
answer applies to you too), and the run's `repo_dir` parameter, which pins the actual target
repo root the same way it does for every node in this workflow.

## Checks

1. **Coverage** — every backlog bullet is assigned to exactly one epic (none dropped, none
   double-counted).
2. **Release boundary** — milestone files exactly preserve the source plan's release target(s).
   When the source checkout already has a milestone, target filename, title, epic membership, and
   order match it; the target has its own generated full Ostler id. Internal implementation phases
   have not been promoted into separate milestones. One MVP release produces one milestone.
3. **Intake ownership** — every backlog id appears in exactly one milestone's `sourceItems`.
   Full ids, not short handles, are persisted. A reused milestone is active and owns the remaining
   intake; a done milestone was not reopened; a disjoint fresh intake received a new milestone.
4. **Coding order** — milestone dependencies put prerequisites before dependents.
5. **Journey clarity** — every epic contains all applicable user journeys, even when its work is
   primarily technical. Each journey names actor, entry point, ordered steps, outcome, required
   states, and the exact segment this epic makes usable.
6. **Each `epic.md`** lets a reviewer understand the shipped experience without reading the backlog:
   actor outcome, all applicable ordered user journeys, delivered experience, guardrails, non-goals, acceptance,
   and running-system source of truth are explicit. Its narrative contains no backlog-id scope table.
7. **Gaps surfaced** — hidden dependencies, role/data/account prerequisites, and product
   decisions are noted, not buried.
8. **Doctor gate** — run `ostler doctor`; do not approve if it reports milestone, status, queue, or
   referential-integrity errors.

## Final response (REQUIRED, exact shape)

After a short markdown summary, return:

```json
{
  "status": "approved" | "needs_rework" | "blocked",
  "notes": "What passed and, for needs_rework/blocked, the specific changes or the question."
}
```

- `approved` — the split is coherent and coding-ordered; authoring can begin.
- `needs_rework` — fixable problems (missing bullet, wrong order, overlap); list them in `notes`.
- `blocked` — a product decision outside your authority is required; put the question in `notes`.
