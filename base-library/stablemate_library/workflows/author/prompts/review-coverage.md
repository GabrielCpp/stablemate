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

- `{{ epic_dir }}/epic.md` — including its `## Seeds` and `## Stories` (the dependency-DAG) sections.
- Each `story.md` under `{{ epic_dir }}/stories/`.

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
3. **Assessability** — each story has concrete acceptance + an assessable QA method. Flag any that
   read as untestable.
4. **Ordering** — dependencies reflect real prerequisites.
5. **Deferral ownership** — every gap a story defers (`disposition: "deferred"` in the knowledge
   record) names an `owner` that exists (a sibling story or an open backlog item). The deterministic
   gate already enforces this; here, catch the subtler version — a surface the stories collectively
   *describe as out of scope* but that no story or backlog item actually owns. An orphaned surface
   is the blank-screen failure; name it in `gaps` so the split/rework stage gives it an owner.
{% block repo_review_rules %}{% endblock %}

## Final response (REQUIRED, exact shape)

After a short markdown summary, return:

```json
{
  "coverage_result": {
    "status": "ok" | "gaps" | "blocked",
    "notes": "Why the coverage is adequate, or the specific stories to add/split, or the question."
  }
}
```

- `ok` — stories fully and granularly cover the epic; move on.
- `gaps` — under-covered or too-coarse; in `notes` name the stories to add or split (the
  story-split stage re-runs with your notes).
- `blocked` — a product decision is required; put the question in `notes`.
