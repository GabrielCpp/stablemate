---
agent: agent
---

# Gather surface knowledge: `{{ workhorse_var('story_slug') }}`

You are the **knowledge-gathering** stage. Before a story is written, build (or enrich) the
durable, structured **knowledge record** for the surface this story touches, so that downstream
authoring, planning, implementation, and QA all read *grounded* facts instead of re-investigating
(and hallucinating) the page on every run.

The record is the **reproducible, accumulating source of derived truth** for the surface. It is
**not** the same as `features/`: `features/` is the human-seeded description of *what the app does
and its user journeys* (the feature set); the knowledge record is the machine-built fact base. You
read `features/` for intent and write the knowledge record for facts.

`features/` is **human-seeded but not frozen** — keeping the feature set current as you learn is
part of this stage's job. You may **append** a newly-observed user journey or behavior to *this
surface's existing feature doc*, and — when a story genuinely introduces a **new, in-scope** screen
that no feature doc yet covers — **draft a new feature doc for it** (clearly marked as author-drafted;
see "Refresh the feature set" below). One hard limit stands: never rewrite or delete the human's
existing prose — only append to it or add new, clearly-marked docs. Reserve `openGaps[]` for surfaces
you genuinely **cannot scope** or that need an operator decision (an ambiguous product call, a missing
account/credential/prerequisite) — not for every new screen. (The old rule forbade documenting any new
surface because this workflow began as a *rewrite* tool, where every surface already existed; that does
not fit greenfield screens.)

## Inputs (authoritative)

- Epic: `{{ workhorse_var('epic') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
- Knowledge tree root: `{{ workhorse_var('knowledge_dir') }}`
{%- if workhorse_var('features_dir') %}
- Feature-doc root: `{{ workhorse_var('features_dir') }}` — the human-curated docs of what the app does and its user journeys.
{%- endif %}
{%- if workhorse_var('surface_manifest') %}
- Surface manifest: `{{ workhorse_var('surface_manifest') }}` — the site's surface inventory; find THIS surface's entry for its route, components, and (greenfield) `mockup` reference.
{%- endif %}

## Where the record lives

Derive a stable **surface key** from the story's seed items (the surface/route they target — e.g.
`projects-estimation/project-create-form`). Write the record to:

```
{{ workhorse_var('knowledge_dir') }}/<area>/<surface>.md
```

The record is a **Markdown file with a YAML front-matter block**: the leading `---` fence carries
the structured fields (the shape below), and the prose body beneath it is the human-readable
narrative — the per-component `whatItDoes` / `behavior` and per-gap `oldState` / `newState`, written
as readable Markdown rather than escaped JSON strings. Keep the front-matter the machine source of
truth (gates and the writer read it); keep the body in sync as a person-friendly explanation.

**Idempotent:** if the record exists, **enrich** it — never discard prior components/gaps. Re-run
must converge (recompute remaining gaps, not duplicate them). Record `provenance` (which sources
you read + an iteration marker) so staleness and progress are visible.

## The core rule: observe by interaction + code, NOT by screenshot

A static screenshot is **evidence, not truth**. A captured frame does not reveal a picker that
opens on click, a search box that filters on type, a `<select>`'s full option set, an accordion's
hidden panels, a modal, or an async/loading state — so an agent that "reads the screenshot" never
learns those components exist or how they behave. **Enumerate components from the live DOM and the
code that declares them, confirmed by *interacting* with the surface** (open the picker, type in
the search, expand the panel, trigger the modal, submit the form). Apply this to **every**
interactive component — never infer a dropdown's contents, a picker's options, or a modal's
existence from a screenshot; confirm by interacting and cross-checking the code.

## What to gather

Build a **two-sided record**: the **intended** behavior (the source of truth) vs. the **current**
build, where the **gap between them is the deliverable**.

1. **Intended side (`old[]`, the source of truth).** Establish what the surface is supposed to be
   from this project's authoritative sources — `features/` (intent/goals) plus any design / spec /
   reference the repo provides. Record each intended component and where its data is meant to come
   from.
{%- if workhorse_var('features_dir') %}
   - **Read this surface's feature doc** under `{{ workhorse_var('features_dir') }}` (and its
     manifest entry if a `surface_manifest` is set). Record the documented **user journeys** —
     the typical end-to-end use cases — into `journeys[]` (each `{id, name, surface, steps[]}`).
     These become journey-level acceptance criteria the story must include. Add the doc path to
     `provenance.sourcesRead`.
   - **Refresh the feature set.** If interacting with the surface reveals a real user journey or
     behavior that the feature doc does **not** yet capture (and it belongs to *this* documented
     screen), append it to that feature doc rather than letting the doc drift stale. Add it under a
     clearly-marked, machine-distinguishable section — e.g. a trailing `## Discovered behaviors
     (added by author workflow)` block — using the same `## Title (route: …, area: …)` heading
     convention the inventory build reads, so the next `build_inventory` picks it up. **Additive
     only**: append bullets/journeys; never edit or remove the human's existing prose. Note the
     refresh in `provenance` and in your final `notes`.
   - **Document a new in-scope screen.** If the story is meant to build an **entirely new screen**
     that no existing feature doc covers, create a new `{{ workhorse_var('features_dir') }}/<surface>.md`:
     a short, human-readable feature doc with a `## <Title> (route: …, area: …)` heading (the same
     convention `build_inventory` reads), an Overview of what the screen is for, and the user
     journey(s) it enables. Mark it clearly as author-drafted (e.g. a leading
     `> Drafted by the author workflow — review.` note) and never overwrite an existing doc. This lets
     `build_inventory` pick the surface up so the coverage/grounding gates resolve and the writer has a
     doc to ground its Acceptance Criteria. Only fall back to `openGaps[]` when the new surface is a
     genuine scope/product decision you cannot settle — record the precise question/prerequisite there.
{%- endif %}
   - **Enumerate context-conditional chrome and transient feedback as first-class facts.** For any
     component whose presence changes by context (global nav, a project picker that shows outside a
     project but is hidden inside one, breadcrumbs), record `chromeContext` (`presentOn` /
     `absentOn`). For any feedback that appears then clears (save flash/toast, inline validation,
     optimistic UI), set the component/gap `feedbackKind: "transient"`. These let the writer plan a
     presence/absence and an appear-then-disappear AC, instead of those being caught only by luck at QA.
2. **Current side (`new[]`, the build).** Drive the **running build** for this surface using the
   repo's local-run / QA skill{% if isUsingInstruction('visual-fidelity-qa') %} (`{{ instruction_ref('visual-fidelity-qa') }}`){% endif %} — bring it up, navigate to the surface as a user, interact with it, and read the code + API (OpenAPI / route / component) to record what currently exists and where its data comes from. If the surface is **unreachable** (blank screen, 403, missing nav entry, never-loads), that is itself a gap — record it as `kind: "unreachable"`.
3. **GAP = classified diff intended→current.** For every component/behavior that is
   missing/broken/divergent/unreachable in the current build vs. the intended source of truth, emit
   a `gaps[]` entry with `oldState` (intended), `newState` (current), `kind`, `dataSource`, and
   `evidence`. This list is the actionable worklist the story will scope from. Default each gap's
   `disposition` to `"scoped"`; the write-story stage decides which gaps a story actually closes
   vs. `deferred` (with an `owner`) vs. `dropped`. **Crucially, do not silently omit a
   component you observed but that this surface's story will not build** — record it as a gap so the
   writer must give it a `disposition` (and, if deferred, an owner). A surface left out of the
   record is the orphan that ships blank.

A repo that **rebuilds an existing system** grounds the intended side against that running reference
system (capturing its real UI as evidence) rather than a static spec — but that repo-specific "how
to observe the source of truth" comes from its flavor + skills (below), not this generic prompt.

If a surface genuinely cannot be observed without an operator-only prerequisite (account, data,
credential, deploy), record it under `openGaps[]` with the precise prerequisite and return
`status: "blocked"` — **never guess** a component or data source.

{% block repo_gather_rules %}{% endblock %}

## Record shape

The structured fields live in the YAML **front-matter** (validated by
`scripts/validate-knowledge.py`); the long-form narrative lives in the Markdown body. Write the file
exactly like this — front-matter first, then a readable body:

```markdown
---
surface: <area>/<surface-key>
route: <new route/path, or ''>
sourceRefs:
  features: <features/<area>/<screen>.md, if any>
  legacy: <legacy URL + template/controller, or ''>
  openapi: ["<operationId or METHOD /path>"]
  newCode: ["<new route/component file>"]
old:
  - name: <ComponentName>
    type: <widget|view|method|…>
    dataSource: { kind: api|computed|static|legacy, endpoint: "", field: "", template: "" }
    chromeContext: { presentOn: [], absentOn: [] }
    feedbackKind: transient|steady
    entryPoint: ""
new: []        # same shape as old; [] if nothing exists yet
gaps:
  - id: <kebab-id>          # stable handle the story's Acceptance Criteria reference
    component: <ComponentName>
    kind: missing|broken|divergent|unreachable
    chromeContext: { presentOn: [], absentOn: [] }
    feedbackKind: transient|steady
    disposition: scoped|deferred|dropped
    owner: ""               # required iff deferred: a story slug or open backlog item id
    dataSource: { kind: "", endpoint: "", field: "", template: "" }
    evidence: { oldShot: "", newShot: "" }
openGaps:
  - { what: "", prerequisite: "" }
journeys:
  - id: <kebab-id>
    name: ""
    surface: ""
    steps: ["..."]
provenance:
  sourcesRead: ["..."]
  iteration: 1
---

# Surface knowledge: <area>/<surface-key>

## Components (intended → current)

### <ComponentName> (old)
<whatItDoes — plain prose.> 
**Behaviour:** interaction / options / async / states.

## Gaps

### <kebab-id> — <component> (<kind>)
**Intended (old):** <what the source of truth says it should be.>
**Current (new):** <what the build does today.>
```

Put `whatItDoes` / `behavior` (per component) and `oldState` / `newState` (per gap) in the body
prose; the front-matter keeps the structured/enum fields. Every `gaps[].id` is a stable handle the
story's Acceptance Criteria reference — keep ids stable across re-runs.

## Final response (REQUIRED, exact shape)

```json
{
  "gather_result": {
    "status": "gathered" | "blocked",
    "surface": "<area>/<surface-key>",
    "record": "<knowledge_dir>/<area>/<surface>.md",
    "gapCount": <int>,
    "notes": "What was observed + gaps found, or the blocking prerequisite."
  }
}
```
