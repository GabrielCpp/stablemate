---
agent: agent
---

# Write the epic: `{{ workhorse_var('epic') }}`

You are the **per-epic writing** stage. Research this one epic's scope, author its `epic.md`
narrative, and record its **seeds** — the durable, itemized record of everything in scope for the
epic — into the epic's `## Seeds` section via `ostler seed add`. You do NOT write stories here; that
is the next stage.

## Inputs (authoritative)

- Epic slug: `{{ workhorse_var('epic') }}`
- Epic directory: `{{ workhorse_var('epic_dir') }}`
- Backlog file: `{{ workhorse_var('backlog') }}`

## Required reading

- This epic's current `{{ epic_dir }}/epic.md` and the backlog bullets it covers.
- `{{ instruction_ref('write-epics-and-stories') }}`, `{{ instruction_ref('story-docs') }}`.

> Existing epics are references, not templates: use them only as a pointer to which surfaces exist,
> then re-research and re-verify every fact against the source-of-truth and the live code. Take
> structure from `{{ instruction_ref('story-docs') }}`, not from them.
{% block repo_epic_rules %}{% endblock %}
- `{{ epic_dir }}/context.md` when present — operator answers to earlier questions.
- Any existing **surface knowledge records** under `{{ workhorse_var('knowledge_dir') }}` for the
  surfaces this epic touches — they are accumulated, grounded old↔new facts (components, data
  sources, gaps) from earlier runs. Reuse them as research input; do not re-derive what they
  already establish.
- The codebase areas this epic touches — enough to enumerate its in-scope items accurately.
{%- if isUsingInstruction('react-router') %}
- The relevant web skills: `{{ instruction_ref('react-router') }}`, `{{ instruction_ref('react-router-architecture') }}`, `{{ instruction_ref('web-api') }}`.
{%- endif %}
{%- if isUsingInstruction('go') %}
- The relevant Go skills: `{{ instruction_ref('go') }}`, `{{ instruction_ref('go-architecture') }}`.
{%- endif %}
{%- if isUsingInstruction('flutter') %}
- The relevant Flutter skills: `{{ instruction_ref('flutter') }}`, `{{ instruction_ref('flutter-architecture') }}`.
{%- endif %}

## Task

1. **Research the epic scope — per item, grounded in the codebase.** Expand each backlog bullet
   for this epic into the concrete, distinct **in-scope items** (surfaces, behaviors, fixes) the
   epic must deliver. Decompose coarse bullets — e.g. "the report button and the reports are
   missing" becomes separate items for the navigation control AND the reports view if they are
   distinct work. For **each** item, actually look at the code: find the surface's current route/
   component (or confirm it's missing), the corresponding source-of-truth reference (design/spec,
   or the legacy surface for a rewrite), the backing API, and any role/data/account prerequisite.
   Record those findings on the seed (below) — this is
   the detail the story-split and per-story stages depend on; bare labels produce bad story
   boundaries. (The per-story stage will research each surface in full depth and capture
   evidence; here you research enough to define and size the items correctly.)
2. **Author `{{ epic_dir }}/epic.md`** (the body was scaffolded by `ostler create epic`; complete
   it): goal, why-this-epic, **method** (how quality is judged — name the source-of-truth
   explicitly), a scope table, and epic-level acceptance. Use the canonical structure from
   `{{ instruction_ref('story-docs') }}`. If a prior epic covered this surface, state that this
   epic **supersedes** it and why.
3. **Record each seed** into the epic's `## Seeds` section with `ostler seed add` (ostler owns the
   mutation — do not hand-edit the section):

   ```bash
   ostler seed add {{ epic }} <short-kebab-id> \
     --status researched \
     --summary "<one line>" \
     --surface "<what exists today: route/component path, or 'missing'>" \
     --legacy-surface "<legacy URL/route + template, or design/spec ref>" \
     --backing "<API endpoint(s)/service the surface uses, if known>" \
     --prerequisites "<role/account/data needed to reach it, or 'none'>" \
     --source-bullet "<verbatim backlog bullet>"
   ```

   Every backlog bullet for this epic must map to ≥1 seed. The seed ids are stable handles the
   story-split stage passes to `ostler create story --covers` (the coverage check depends on it).
   The research fields (`--surface`, `--legacy-surface`, `--backing`, `--prerequisites`, plus any
   key parity points / risks in the `--summary` and the seed's prose body) carry the detail that
   makes the story split and the per-story write effective — fill them from real research, not
   guesses; if an item genuinely can't be researched, say so in the seed's summary/prose (and
   return `blocked` if it needs an operator answer).

## Idempotency

If `epic.md` and its `## Seeds` already exist, refine and complete them — do not discard prior
seeds (re-running `ostler seed add` on an existing seed id updates it rather than duplicating).

## Final response (REQUIRED, exact shape)

```json
{
  "write_epic_result": {
    "status": "complete" | "blocked",
    "notes": "Items recorded, or the blocking question for the operator."
  }
}
```
