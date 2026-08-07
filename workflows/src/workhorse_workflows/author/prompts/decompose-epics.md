---
agent: agent
---

# Decompose the {{ repo.name | title }} backlog into milestones and coding-ordered epics

You are the **epic-split** stage of the author workflow. Turn a high-level feature backlog into
a milestone graph and a set of **coding-ordered epics** that the coder workflow can later execute.
You do NOT write stories yet — only milestone files and a one-screen `epic.md` skeleton per epic.

## Inputs (authoritative — use exactly as given)

- Backlog file: `{{ workhorse_var('backlog') }}` (resolved by ostler; use it as given)
- Epics directory: `{{ workhorse_var('epics_dir') }}`

> The backlog is a **live worklist**: once an epic is fully authored, its consumed bullets are
> pruned from the backlog automatically. So treat whatever bullets remain in the file as the
> outstanding scope, and never re-create an epic that already exists in the milestone graph.
> Before this turn, author intake assigns an Ostler id to every unnamed direct work bullet. Treat
> bracketed ids as opaque identities; never derive identity from bullet prose.

## Required reading

- The backlog file above (every bullet is in scope — none may be dropped) **except** bullets
  under a `## Filed by coder` heading. Those are adjacent-defect/hardening findings the coder
  workflow's own fix loop drains and prunes directly — do not decompose them into an epic, and
  do not remove them yourself; leave that section alone.
- This repo's **planning method** — research-first, dependency-ordered, MVP-aware decomposition:
  {{ find_by_tags("planning") | default("(none installed — decompose research-first and dependency-ordered, and say so in the epic)", true) }}.
- Its **artifact grammar** — the canonical layout, milestone files under `docs/milestones/`,
  the `epic.md` body grammar, and bookkeeping rules:
  {{ find_by_tags("planning", "docs") | default("(none installed — mirror the best-formed existing epic)", true) }}.
- Existing milestones and epics, when present — to avoid duplicate milestone or epic folders.
  Existing epics are references, not templates — re-verify them against the source-of-truth.
- Any source roadmap or product plan linked from the backlog. Preserve its named release boundary;
  do not reinterpret implementation phases inside one release as separate milestones.
- When a linked source roadmap belongs to another checkout, inspect that source checkout's existing
  `docs/milestones/` and the epic docs its milestone lists. An existing source milestone is
  authoritative for its filename, title, epic membership, and coding order. Reproduce that
  planning boundary in the target sandbox rather than inventing a synonymous milestone or a new
  epic partition. Its allocated `id` belongs to that source graph and is not copied: a fresh target
  milestone receives its own generated Ostler id. Rewrite each epic's narrative into the
  journey-readable grammar below; do not copy prior status markers or stale claims.
- `{{ epics_dir }}/_author-context.md` when present — operator answers to earlier questions.

> Existing epics are references, not templates: take structure from the rubric and the
> artifact grammar above, re-verify every factual claim against the source-of-truth,
> and never copy a prior epic's status markers. Where a prior epic covers the same surface, your new
> epic **supersedes** it (note that explicitly).
{% block repo_decompose_rules %}{% endblock %}

## Method

1. **Plan from existing docs only.** For each backlog bullet, use the backlog, its linked source
   plans, existing milestone /
   epic docs, and any existing OKF references already linked from those docs. Do not inspect the
   running app or source code to discover surfaces, and do not create or update OKF feature-book
   nodes; the OKF book is produced by the okf-builder and is only referenced by author.
2. **Preserve release milestones.** A milestone is a release/product gate, not a foundation,
   contract, reader, authoring, or publishing phase. One MVP target means one milestone; internal
   roadmap phases stay inside it. Preserve an existing source milestone's filename, title, epic
   membership, and order exactly even when authoring into a separate sandbox.
3. **Own and drain this intake.** Every eligible bracketed backlog item belongs to exactly one
   milestone's `sourceItems` using its full id, never a short display handle. Reuse an existing
   target milestone only when it is not done, the remaining ids are already a subset of its
   `sourceItems`, and the product outcome is unchanged. A disjoint fresh intake creates a new
   milestone. For partial overlap plus new ids, extend the active milestone only when the outcome is
   unchanged; otherwise return `blocked` with the precise split question. Never reopen a done
   milestone.
4. **Make every epic journey-readable.** Group cohesive, coding-ordered work into epics, then put all
   user journeys that the epic delivers or materially advances inside that epic. A journey names its
   actor, entry point, ordered observable steps, outcome, required states, and exactly what this epic
   makes usable. Never make the reader reconstruct delivery from a list of technical components.
5. **Order in coding order.** Sequence milestone dependencies first, then epics within each
   milestone. Do not express that order by writing `{{ epics_dir }}/index.md`; milestones are the
   ordering source of truth.
6. **Surface gaps now, not later.** If a bullet hides a dependency, a role/data/account
   prerequisite, or an ambiguous product decision, note it in the epic's `epic.md` (and, if it
   truly blocks decomposition, return `blocked` with the question).

## Idempotency

This stage may re-run. Create only missing milestones/epics and refine existing milestone files —
never clobber existing epics or reorder ones already authored unless an operator answer in
`_author-context.md` tells you to. Do not run `ostler todo add`, `ostler todo prune`, or otherwise
write `{{ epics_dir }}/index.md`.

## Output artifacts

Create or update one milestone file per release target established by the backlog and linked source
plan under `docs/milestones/`. Create a missing milestone with Ostler so its id is generated:

```bash
ostler create milestone docs-app-mvp --title "Docs App MVP" \
  --source-items <full-id>,<full-id> --json
```

The readable slug determines the filename and the content determines the title; Ostler determines
the immutable full id. A reused milestone keeps its id and updates ownership with
`ostler milestone set-source-items <slug> <full-id>...`. Never write a short handle into Markdown:
handles are display-only and can lengthen after a collision. Each milestone may contain many epics:

```markdown
---
type: milestone
id: AUTH-01KZ...
title: Docs App MVP
status: planned
dependsOn: []
sourceItems:
  - AUTH-01KY...
epics:
  - docs-app-foundation
  - docs-app-schema-core-library
---
# Docs App MVP

The product/workflow gate this milestone proves.
```

For each new epic, create it with `ostler` (which allocates the id and scaffolds the folder):

```bash
# Allocates the id and scaffolds the folder with empty ## Seeds + ## Stories. ostler numbers
# the directory in creation order, so the folder is <NNNN>-<slug>, not <slug> — read the name
# it created back out of the JSON rather than assuming it:
CREATED=$(ostler create epic <slug> --title "<Epic Title>" --json)
EPIC_ID=$(jq -r .id <<<"$CREATED")      # → e.g. "ACME-7" (prefix is uppercased by ostler)
EPIC_DIR=$(jq -r .name <<<"$CREATED")   # → e.g. "0003-<slug>"
# Do not run `ostler todo add`; milestone files are the ordering source of truth.
```

Use a kebab `<slug>`; ostler prefixes it with the sequence number. Then author the epic narrative
into the scaffolded `{{ epics_dir }}/$EPIC_DIR/epic.md` body (`ostler path epic <slug>` prints that
directory at any time). The human-facing body must contain `## User Outcome`, `## User Journeys`,
`## Delivered Experience`, `## Guardrails`, `## Non-Goals`, `## Acceptance`, and `## Method`, followed
by the scaffolded `## Seeds` and `## Stories`. Under `## User Journeys`, add one `###` section for
every journey applicable to the epic; each names the actor and entry point, lists ordered observable
steps, states the outcome, and identifies the segment this epic delivers. `## Delivered Experience`
must name what a reviewer can concretely use when the epic ships; method must name the running system
as source of truth. Do not add a scope table or cite backlog ids in this narrative. Backlog
traceability belongs to later machine-owned seed metadata.

## Final response (REQUIRED, exact shape)

After any markdown notes, return this JSON object as your final message:

```json
{
  "status": "complete" | "blocked",
  "notes": "Epics created/updated and their coding order, or the blocking question."
}
```

Use `blocked` only when a product decision you cannot make prevents grouping the backlog; put the
precise question in `notes` (the workflow records it for the operator).
