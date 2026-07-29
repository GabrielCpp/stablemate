---
agent: agent
---

# Write the story: `{{ workhorse_var('story_slug') }}`

You write a **bare-minimum story**: just enough for the coder to know the goal and how it will be
judged. Two sections of substance — **Context** and **Acceptance Criteria** — and nothing else.

The coder workflow owns the depth. It plans, implements across **as many iterations as the goal
needs**, files **follow-ups** for work the goal turns out to require, and runs real QA against your
acceptance criteria. An over-specified story does not make the coder more correct — long, detailed
stories have still shipped with whole defects unnoticed — it just rots and misleads.

> Do NOT enumerate components, data sources, file paths, gap tables, parity matrices, dependencies,
> required skills, or an implementation plan. If you are describing *how* to build it, stop — that
> is the coder's job. Your job is *what* and *why*, plus *how it's judged*.

## Inputs (authoritative)

- Epic: `{{ workhorse_var('epic') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Operator answers: `{{ workhorse_var('story_dir') }}/context.md` when present.
{%- if workhorse_var('mockup_path') %}
- Design mockup (new screen): `{{ workhorse_var('mockup_path') }}` — a generated visual reference in the
  app's style; link it from Context as the source of truth the criteria are judged against.
{%- endif %}
{%- if workhorse_var('features_dir') %}
- **OKF book root**: `{{ workhorse_var('features_dir') }}` — the surface documentation, already built
  from the code by the okf-builder. **Read it; never write to it.** This is where the story's
  grounding comes from — see *Ground the story in the book* below.
{%- endif %}

## Required reading

- The parent `epic.md` — read its `## Stories` section to find THIS story's entry (its `covers`
  edge) and its `## Seeds` section for the seeds that story covers, so the Context reflects the
  right scope.
- `{{ instruction_ref('story-docs') }}` — the story file layout.

{%- if workhorse_var('features_dir') %}

## Ground the story in the book (cite node ids)

The OKF book under `{{ workhorse_var('features_dir') }}` already describes every surface the code
has — screens, components, interactions, flows, endpoints, commands. **That gathering is done; do
not redo it and do not add to it.** Your job is to find the handful of nodes this story touches and
*cite* them.

A node's id **is** its location: a repo-relative path for a whole document (`docs/okf/web/settings.md`),
and `path#anchor` for a section inside one (`docs/okf/web/settings.md#profile-form`). So a citation is
an ordinary markdown link — write the id verbatim as the href:

```markdown
Covers the profile form on [the settings screen](docs/okf/web/settings.md), specifically
[Save profile](docs/okf/web/settings.md#save-profile).
```

Rules:

- Cite from `## Context`, **at least one** node, and only nodes the story actually works on.
- Copy ids **exactly** as the book spells them. A link that resolves to no node fails the grounding
  gate — which is the point: a mistyped id must not read as grounding.
- Cite the *narrowest* node that is true — the component/interaction section over the whole screen —
  and add the screen only for orientation.
- A citation is a pointer, not a paste. Do not copy the node's contents into the story.
- If this story's surface genuinely has no node yet (a new screen), there is nothing to cite from the
  book — link the design mockup instead and say in one clause that the surface is new.
{%- endif %}

{% block repo_authoring_rules %}{% endblock %}

## Context (what & why — short)

A few sentences in the user's terms: what surface or behaviour this story is about, where it lives,
and what "done" means at a high level (e.g. "at parity with the legacy X editor"). Name the surface
by **linking its OKF node ids** (above) so the scope is grounded rather than asserted. Link the
**visual reference** the criteria are judged against: a running legacy surface (rewrite projects),
or — when there is no live reference — the **design mockup** for this surface (the `mockup_path` input
above if set, else the manifest entry's `mockup` image under the repo's mockup dir). A spec, legacy
route, or captured evidence all qualify. This orients the coder; it is **not** a spec and not a build plan.

## Acceptance Criteria (how it's judged — observable, user-facing)

A checklist of the **observable outcomes** that must be true when the goal is met, phrased as what a
person *using the app* would see or do — never as DOM selectors or implementation details:

- Behaviour and correctness (e.g. "typing in one field changes only that field; checking one box
  checks only that box").
- Visible content (e.g. "section titles and field labels show the translated names, not internal
  codes").
- Parity with the source of truth (e.g. "the page shows the same sections, navigation, and controls
  as the legacy editor").
- The states the goal implies: happy path **plus** empty / loading / error / reachability where they
  matter.

{%- if workhorse_var('features_dir') %}
The criteria MUST also cover what the nodes you cited say — read from the book, never invented:

- **The documented user journey(s)** — the `flow` nodes the cited surface takes part in: at least
  one AC that a user can complete the typical end-to-end use case (e.g. "a signed-in user can open
  the editor, change a value, save, and see it persisted on reload").
- **Context-conditional chrome** — a component the book says appears only in some contexts: an AC
  for its presence *and* absence in each context the story touches (e.g. "the project picker is
  shown on the projects list but hidden inside an open project").
- **Transient feedback** — an interaction whose outcome the book describes as a flash/toast/
  confirmation: an AC that the feedback **appears then clears** (e.g. "saving shows a confirmation
  that then disappears"), not merely that a control exists.
{%- endif %}

One check per item, each independently verifiable by **looking at or using the running app**. These
criteria are the contract the coder's QA verifies against the source of truth, so make them about
real, user-visible behaviour — not the mere presence of an element in the DOM.

## Write `{{ workhorse_var('story_path') }}`

`ostler create story` already scaffolded this `story.md` with `## Context`, `## Acceptance
Criteria`, and `## Implementation Status` (`- **Status**: Not started`). Fill in the **Context** and
**Acceptance Criteria** bodies — and only those. Add no other sections. The result should read:

```markdown
# Story: <title>

## Context

<a few sentences: the goal, where it lives, what done means, link to source of truth>

## Acceptance Criteria

- <observable, user-facing outcome>
- <…>

## Implementation Status

- **Status**: Not started
```

Do not add Description, Evidence, Verification setup, QA, Dependencies, or Required skills sections —
the coder discovers all of that. Leave `## Implementation Status` as scaffolded; do not hand-edit
the `- **Status**:` line — status transitions go through `ostler set-status <slug> "<status>"`
(the coder owns them).

## No open questions

Resolve the call or leave it out — do not ship `TBD` / `TODO` / `open question` / "decide whether".
If a product decision genuinely needs the operator and you cannot settle it, return
`status: "blocked"` with the precise question in `notes` instead of writing indecision into the story.

## Final response (REQUIRED, exact shape)

```json
{
  "write_story_result": {
    "status": "written" | "blocked",
    "notes": "one line: the goal this story sets, or the blocking question."
  }
}
```
