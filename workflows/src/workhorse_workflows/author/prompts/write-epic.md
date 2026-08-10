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

- This epic's current `{{ epic_dir }}/epic.md`, especially its `## User Journeys`, and the backlog.
  Determine its bullet ownership from the journeys and delivered boundary stated in the epic, while
  checking neighboring epics so the same bullet is not claimed twice.
- This repo's planning method — how it decomposes and sizes work:
  {{ find_by_tags("planning") | default("(none installed — follow the structure the existing epics establish)", true) }}.
- Its **artifact grammar** — the canonical `epic.md` body and story layout:
  {{ find_by_tags("planning", "docs") | default("(none installed — mirror the best-formed existing epic)", true) }}.

> Existing epics are references, not templates: use them only as a pointer to which surfaces exist,
> then re-research and re-verify every fact against the source-of-truth and the live code. Take
> structure from the artifact grammar above, not from them.
{% block repo_epic_rules %}{% endblock %}
- `{{ epic_dir }}/context.md` when present — operator answers to earlier questions.
{%- if workhorse_var('features_dir') %}
- The **OKF book** under `{{ workhorse_var('features_dir') }}` for the surfaces this epic touches —
  the existing surface documentation (screens, components, interactions, flows). Read it as the only
  surface inventory author may use, cite its node ids when relevant, and do not re-derive or extend
  what it establishes. **Never write to it**: the OKF book is built by okf-builder, not author.
{%- endif %}
- The layer entrypoints this repository installs, for the layers this epic actually touches:
  {{ find_by_tags("entrypoint") | default("(none installed — read the repo's own architecture docs)", true) }}.
  Each one is the root of its layer and fans out to that layer's own architecture, API and testing
  siblings — follow those links for the layers in scope, and open nothing for the layers that are not.

## Task

1. **Research the journey delivery from existing docs and OKF only.** Expand each backlog bullet for this
   epic into the concrete, distinct **in-scope items** (surfaces, behaviors, fixes) the epic must
   deliver. Decompose coarse bullets — e.g. "the report button and the reports are missing" becomes
   separate items for the navigation control AND the reports view if existing OKF/docs show they are
   distinct work. For **each** item, use existing OKF nodes, design/spec references, legacy-reference
   docs, and operator context already present. Do not inspect the running app or source code to
   discover surfaces, routes, components, APIs, or prerequisites, and do not create OKF nodes. If the
   existing docs/OKF cannot establish an item, record that uncertainty in the seed and return
   `blocked` if it needs an operator decision.
2. **Author `{{ epic_dir }}/epic.md`** around its concrete delivery boundary. Before `## Seeds`, the
   human-facing body must contain `## User Outcome`, `## User Journeys`, `## Delivered Experience`,
   `## Guardrails`, `## Non-Goals`, `## Acceptance`, and `## Method`. The journey is an ordered
   sequence of observable actor steps. Add one `###` subsection under `## User Journeys` for every
   journey applicable to this epic, naming actor, entry point, steps, outcome, required states, and
   the exact segment this epic delivers. Delivered experience names the URL, screen, command,
   document, or operation a reviewer can concretely use; method names the running system as source
   of truth. Do not add a scope table or cite backlog ids in those narrative sections.
   `sourceBullet` below is machine-owned pruning metadata. If a prior epic covered this surface,
   state that this epic supersedes it and why without copying its technical framing.
3. **Record each seed** into the epic's `## Seeds` section with `ostler seed add` (ostler owns the
   mutation — do not hand-edit the section):

   ```bash
   ostler seed add {{ epic }} <short-kebab-id> \
     --status researched \
     --summary "<one line>" \
      --surface "<existing OKF node id / documented surface, or 'missing from OKF'>" \
      --legacy-surface "<legacy/reference doc or design/spec ref, if documented>" \
      --backing "<documented API/service reference, if present>" \
     --prerequisites "<role/account/data needed to reach it, or 'none'>" \
     --source-bullet "<verbatim backlog bullet>" \
     --layer <frontend|backend|infra> [--layer ...] \
     --service <service-or-package> [--service ...]
   ```

   `--layer` and `--service` are both repeatable, and a seed routinely carries several of each:
   one seed spans a screen and the API behind it. Classify by what the work *touches*:

   | Layer      | Use it when the seed changes                                        |
   | ---------- | ------------------------------------------------------------------- |
   | `frontend` | a user-visible screen, view, or component                            |
   | `backend`  | a service, API, handler, job, or data access                         |
   | `infra`    | build, deploy, CI, configuration, or schema/migration                |

   These are load-bearing, not bookkeeping: a story covering a seed tagged `frontend` gets a
   design-mockup turn, and one whose seeds are all `backend`/`infra` skips it. Tag every seed —
   a seed left untagged keeps the mockup turn, so an omission costs a wasted design pass rather
   than silently dropping one. `--layer` takes only the three tokens above; anything else is
   rejected. `--service` is free text: use the repo, package, or service directory name.

    Every backlog bullet assigned to this epic's delivered journeys must map to ≥1 seed. The seed ids are stable handles the
   story-split stage passes to `ostler create story --covers` (the coverage check depends on it).
   The research fields (`--surface`, `--legacy-surface`, `--backing`, `--prerequisites`, `--layer`,
   `--service`, plus any
   key parity points / risks in the `--summary` and the seed's prose body) carry the detail that
   makes the story split and the per-story write effective — fill them from real research, not
   guesses or fresh app/code discovery; if an item genuinely can't be established from existing docs
   and OKF, say so in the seed's summary/prose (and return `blocked` if it needs an operator answer).

## Idempotency

If `epic.md` and its `## Seeds` already exist, refine and complete them — do not discard prior
seeds (re-running `ostler seed add` on an existing seed id updates it rather than duplicating).

## Final response (REQUIRED, exact shape)

```json
{
  "status": "complete" | "blocked",
  "notes": "Items recorded, or the blocking question for the operator."
}
```
