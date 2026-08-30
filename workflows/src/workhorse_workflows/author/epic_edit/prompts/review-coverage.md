---
agent: agent
---

# Adequacy review: do `{{ workhorse_var('epic') }}`'s stories cover the epic?

You are the **epic-coverage adequacy** judge. The deterministic validator already confirmed every
seed is claimed by some story and the graph is valid. Your job is the judgment a script
can't make: are the stories **granular and complete enough** to actually deliver the epic — or
are they **too few / too coarse** to be implemented and assessed?

## Inputs (authoritative)

- Epic: `{{ workhorse_var('epic') }}`
- Epic directory: `{{ workhorse_var('epic_dir') }}`

## Required reading

- `{{ epic_dir }}/epic.md` — including its `## Seeds` and `## Stories` (coverage) sections.
- Each `story.md` under `{{ epic_dir }}/stories/` — its `## Dependencies` section is the
  dependency DAG.
- The repo's **planning method** — the slicing and sequencing rules the split is held to:
  {{ find_by_tags("planning") | default("(none installed — hold the split to vertical slices: first story is the thinnest end-to-end journey step, later stories widen it)", true) }}.

## What stage this is — story bodies are empty by design here

The stage before you **splits** the epic: it decides the set of stories and records each one's
title and `covers` under `## Stories`, and scaffolds a `story.md` per story carrying its
blockers. It does
not write story bodies — the per-story authoring stage does that *after* coverage is settled.

So at this point every `story.md` is expected to be a scaffold with empty `## Context` and
`## Acceptance Criteria`, `## Non-Functional Acceptance Criteria`, or `## Technical Notes`.
**That is the correct state, not a defect.** Do not return `gaps` for a
blank story body, an absent QA method, or missing acceptance text; the split stage is structurally
unable to fix them, so such a verdict only sends the graph around a lap that changes nothing.

Judge coverage against `epic.md` — its `## Seeds` (with their researched `surface`, `backing`,
`prerequisites`), the `## Stories` coverage edges, and each story's `## Dependencies`. Read the
`story.md` files for whatever they *do* carry (a title, an existing body on a re-run), and let their
scaffolded sections pass without comment.

## Checks

1. **Completeness** — every part of the epic's stated scope/acceptance is reflected in some
   story, not just every seed id mechanically tagged. Look for scope described in `epic.md` that
   no story actually delivers.
2. **Granularity** — no story is so coarse it can't be independently implemented and QA-assessed
   (the "restore everything" anti-pattern). Recommend splitting where needed.
   - Also flag the **opposite** defect: a story with **no concrete deliverable** — one whose work
     is purely "verify already-built X matches" with nothing it changes or creates. That belongs
     as acceptance/QA on the story that builds X, not as a standalone story. Recommend folding it
     in (return `gaps` naming the merge).
3. **Assessability** — each story is *scoped* so that acceptance and a QA method can be written for
   it: it names a concrete deliverable on a nameable surface. Judge the scope (title + the seeds it
   `covers`), **not** the body — a story whose acceptance section is still empty is on schedule, but
   one scoped as "improve the experience" is untestable no matter what gets written into it later.
4. **Ordering** — dependencies reflect real prerequisites.
5. **Vertical slicing** — the dependency-root story is a walking skeleton: a thin end-to-end
   journey step in the running system, not a "set up the backend" / "create the data model"
   layer. Every story answers *"after this is green, what can the actor do that they couldn't
   before?"* — a story with no answer is a horizontal slice; return `gaps` naming the journey
   story it should fold into. Flag layer-ordered sequencing (all storage, then all API, then all
   UI) and dependency edges that exist only because "the layer below comes first".
6. **Deferral ownership** — nothing this epic's stories put out of scope is left unowned. The
   deterministic gate can only see edges that exist (an orphan seed, a dangling dependency); what it
   cannot see is scope the stories collectively *describe* as somebody else's — "the export flow is
   handled elsewhere", "auth is out of scope here" — with no sibling story and no open backlog item
   that actually owns it. An orphaned surface is the blank-screen failure; name it in `gaps` so the
   split/rework stage gives it an owner.
{% block repo_review_rules %}{% endblock %}

## Final response (REQUIRED, exact shape)

After a short markdown summary, return:

```json
{
  "status": "ok" | "gaps" | "blocked",
  "notes": "Why the coverage is adequate, or the specific stories to add/split, or the question."
}
```

- `ok` — stories fully and granularly cover the epic; move on.
- `gaps` — under-covered or too-coarse; in `notes` name the stories to add or split (the
  story-split stage re-runs with your notes).
- `blocked` — a product decision is required; put the question in `notes`.
