---
agent: agent
---

# Decompose the {{ repo.name | title }} backlog into coding-ordered epics

You are the **epic-split** stage of the author workflow. Turn a high-level feature backlog into
a set of **coding-ordered epics** that the coder workflow can later execute. You do NOT write
stories yet — only the epic list, its order, and a one-screen `epic.md` skeleton per epic.

## Inputs (authoritative — use exactly as given)

- Backlog file: `{{ workhorse_var('backlog') }}` (default `docs/backlog.md`)
- Epics directory: `{{ workhorse_var('epics_dir') }}`

> The backlog is a **live worklist**: once an epic is fully authored, its consumed bullets are
> pruned from the backlog automatically. So treat whatever bullets remain in the file as the
> outstanding scope, and never re-create an epic that already exists in the epics queue
> (`ostler todo list`).

## Required reading

- The backlog file above (every bullet is in scope — none may be dropped) **except** bullets
  under a `## Filed by coder` heading. Those are adjacent-defect/hardening findings the coder
  workflow's own fix loop drains and prunes directly — do not decompose them into an epic, and
  do not remove them yourself; leave that section alone.
- `{{ instruction_ref('write-epics-and-stories') }}` — the decomposition method (research-first,
  dependency-ordered, MVP-aware).
- `{{ instruction_ref('story-docs') }}` — the canonical layout, the `epic.md` body grammar, the
  `docs/epics/index.md` queue (managed via `ostler todo`), and bookkeeping rules.
- The epics queue (`ostler todo list`) and existing epics, when present — to avoid duplicate epic
  folders. Existing epics are references, not templates — re-verify them against the source-of-truth.
- `{{ epics_dir }}/_author-context.md` when present — operator answers to earlier questions.

> Existing epics are references, not templates: take structure from the rubric and
> `{{ instruction_ref('story-docs') }}`, re-verify every factual claim against the source-of-truth,
> and never copy a prior epic's status markers. Where a prior epic covers the same surface, your new
> epic **supersedes** it (note that explicitly).
{% block repo_decompose_rules %}{% endblock %}

## Method

1. **Research first.** For each backlog bullet, skim the codebase enough to understand its true
   scope, what already exists, and what it depends on. Do not invent scope from the bullet text
   alone.
2. **Group into epics.** Each epic is a cohesive, shippable goal. Keep epics MECE — every bullet
   lands in exactly one epic, and epics don't overlap.
3. **Order in coding order.** Sequence epics so prerequisites come first (foundations, shared
   shell/navigation, contracts) before the features that depend on them. This order is what
   coder will follow.
4. **Surface gaps now, not later.** If a bullet hides a dependency, a role/data/account
   prerequisite, or an ambiguous product decision, note it in the epic's `epic.md` (and, if it
   truly blocks decomposition, return `blocked` with the question).

## Idempotency

This stage may re-run. **Append** new epics to the queue (`ostler todo add`) and create only
missing epics — never clobber existing epics or reorder ones already authored unless an
operator answer in `_author-context.md` tells you to.

## Output artifacts

For each new epic, create it with `ostler` (which allocates the id and scaffolds the folder), then
queue it:

```bash
# Allocates the id, scaffolds {{ epics_dir }}/<slug>/epic.md with empty ## Seeds + ## Stories:
EPIC_ID=$(ostler create epic <slug> --title "<Epic Title>" --json | jq -r .id)   # → e.g. "pred-7"
# Append the epic to the queue (docs/epics/index.md):
ostler todo add <slug>
```

Use a kebab `<slug>` as the epic folder name. Then author the epic narrative into the scaffolded
`{{ epics_dir }}/<slug>/epic.md` body: goal, why-this-epic, method (how fidelity/quality will be
judged — name the **source-of-truth**, which is the running site, not source templates alone), a
scope table, and epic-level acceptance. Use the canonical structure from
`{{ instruction_ref('story-docs') }}` — do not copy prior epics verbatim. Seeds and stories are
added in the later stages, not here.

## Final response (REQUIRED, exact shape)

After any markdown notes, return this JSON object as your final message:

```json
{
  "decompose_result": {
    "status": "complete" | "blocked",
    "notes": "Epics created/updated and their coding order, or the blocking question."
  }
}
```

Use `blocked` only when a product decision you cannot make prevents grouping the backlog; put the
precise question in `notes` (the workflow records it for the operator).
