---
agent: agent
---

# Split epic `{{ workhorse_var('epic') }}` into stories

You are the **story-split** stage. Decide the epic's stories and record them into the epic's
`## Stories` section via `ostler create story` — slugs, titles, dependencies, and the seeds each
story covers. (`ostler create story` allocates the id, adds the `### <slug>` block under
`## Stories`, and scaffolds the `story.md`.) You do NOT write `story.md` bodies here; the per-story
stage does that next.

## Inputs (authoritative)

- Epic slug: `{{ workhorse_var('epic') }}`
- Epic directory: `{{ workhorse_var('epic_dir') }}`

## Required reading

- `{{ epic_dir }}/epic.md`, especially its `## Seeds` section — the in-scope seeds to cover, each
  already carrying research (`surface`, `legacySurface`, `backing`, `prerequisites`, and the seed's
  summary/prose). **Use that detail to size and sequence stories** — e.g. a seed whose `surface`
  is "missing" plus a separate "fidelity" seed become distinct stories; a `prerequisites` note
  drives a dependency edge. Do not size stories from the one-line summary alone. (Read seeds with
  `ostler list --type seed --epic {{ epic }} --json` if you prefer structured output.)
- `{{ instruction_ref('story-docs') }}` — the `## Stories` grammar (the `covers` / `depends on`
  edges) and slug rules.
- `{{ instruction_ref('write-epics-and-stories') }}` — story sizing/sequencing guidance. Where it
  says "use existing stories as templates", size stories from the **researched seed**, not from how
  any existing epic split the work — existing breakdowns are references, not templates.
{% block repo_split_rules %}{% endblock %}
- `{{ epic_dir }}/context.md` and the epic's existing `## Stories` section when present.

## Task

1. **Cover every seed.** Each seed id in the epic's `## Seeds` must be claimed by at least one story
   via that story's `--covers`. Do not drop scope.
2. **Right-size stories — prefer more, sharper stories over a few coarse ones.** A story should be
   one focused, independently QA-able unit of work. Coarse "restore everything" stories are the
   anti-pattern that produced unverifiable epics; split them.
   - **Every story must have a concrete deliverable — something it *changes or creates*.** A story
     whose work is purely *"verify already-built X still matches"* is **not** a standalone story:
     fold that verification into the acceptance criteria / QA of the story that builds X, or — if
     the surface genuinely needs new work — scope the story around that new work and let the
     parity check ride along as its QA. Watch for this when an epic layers a "fidelity" seed item
     over a surface a sibling story already implements: that's usually one story (build + verify
     parity), not a build story plus a verify story.
3. **Order with `--depends`.** A story depends on another only when it genuinely needs it
   first (e.g. a shared shell/navbar before pages that live in it). Keep the graph acyclic.
4. **Create each story with `ostler` — it allocates the id and scaffolds the files.** Pass a
   kebab `<slug>`; ostler records the `### <slug>` edge block under `## Stories`, allocates the
   story id, and scaffolds `{{ epic_dir }}/stories/<slug>/story.md`:
   ```bash
   ostler create story {{ epic }} <kebab-slug> \
     --title "<title>" \
     --covers <seed-id>,<seed-id> \
     --depends <sibling-slug>,<sibling-slug>
   ```
   Omit `--covers` for a seedless story; omit `--depends` for an independent one.

## Output — the epic's `## Stories` section

Each `ostler create story` call adds a story block under `## Stories` in `{{ epic_dir }}/epic.md`,
carrying its `title`, allocated `id`, `covers` (the seeds), and `depends on` (sibling slugs), and
scaffolds the story's `story.md`. You may add optional `- phase: …` / `- effort: …` bullets to a
story block if the project tracks them. Do NOT write `story.md` body content in this stage.

After creating the stories, run `ostler doctor --epic {{ epic }}` to confirm the graph is acyclic,
every seed is covered, and no edge references another epic.

## Idempotency

If the epic already has stories, extend/refine the set (e.g. add stories to cover an uncovered
seed the coverage gate flagged) — keep stories that already have written bodies. Re-running
`ostler create story` for an existing slug is a no-op for that slug.

## Final response (REQUIRED, exact shape)

```json
{
  "split_result": {
    "status": "complete" | "blocked",
    "notes": "Stories and the seed items each covers, or the blocking question."
  }
}
```
