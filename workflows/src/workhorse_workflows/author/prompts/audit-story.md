---
agent: agent
---

# Adversarially audit a story for coder-readiness: `{{ workhorse_var('story_slug') }}`

The story passed the **structural** validator (it has Context + Acceptance Criteria, a Status
line, no open-decision markers) and a deterministic **grounding gate** (its surface was researched
and, when feature docs are configured, its journey was read). Your job is the part a script
cannot do: **independently re-judge the story and try to REFUTE that it is coder-ready.** You are a
skeptic, not a rubber stamp. A story you cannot break stands; one you *can* break goes back for
rework. Default to suspicion — a structurally-valid story can still be vague, ungrounded, or miss
the surface's documented journey, and the coder will build the wrong thing from it.

You do **not** rewrite the story. You re-derive whether its Acceptance Criteria are something a
coder could actually build and a QA could actually verify, grounded in the researched facts.

## Inputs (authoritative — do not rediscover)

- Epic: `{{ workhorse_var('epic') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
{%- if workhorse_var('features_dir') %}
- **OKF book root**: `{{ workhorse_var('features_dir') }}` — the existing surface documentation, and
  the grounding source of truth. Read it; never write to it. Do not inspect the app or source code to
  discover missing OKF nodes or surfaces.
{%- endif %}

## Read

- the story file — its **Context** and **Acceptance Criteria** are what you judge
{%- if workhorse_var('features_dir') %}
- **the OKF nodes the story cites** — its `## Context` links them by id (a node id is a
  repo-relative path, optionally `path#anchor`). These are the surface's documented components,
  interactions, and flows: what the story claims to work on, in the book's own words.
{%- endif %}
- the epic's `## Seeds` and `## Stories` sections in `epic.md` — the scope this story claims (the
  seeds it covers); the story's own `## Dependencies` section names what blocks it

{% if workhorse_var('prior_audit_findings') %}
## Convergence re-audit

A full independent audit already found, one finding per line as
`<id> [<kind>] <target>: <issue>. Repair: <repair>`:

{{ workhorse_var('prior_audit_findings') }}

Verify every listed finding against the revised story. Return a finding **only** when a listed one
remains unresolved — reusing its `id` so the same defect keeps one name across passes — or when the
repair introduced a concrete regression on the same readiness axes. Do not re-raise an id whose
repair landed, and do not open a new stylistic preference or silently expand the contract: a defect
you could have named in the first lap and did not is one you have forfeited.
{% endif %}

## How to audit — try to refute on each axis

1. **Observable + verifiable.** Each AC must be a thing the journey actor could see or do once the
   coder has built the story. A technical enabler may instead be verified by an operator at the
   running system boundary, but it must name the epic journey step it unlocks. A DOM selector, file
   presence, framework setup, implementation detail, or vague claim ("works correctly", "looks
   right", "is performant") → **refuted**.
2. **Grounded and in scope.** Existing behavior must trace to its cited OKF node or other cited
   evidence. New behavior is grounded when the epic seed/story entry puts the goal in scope and the
   Acceptance Criteria make the necessary product and interaction choices explicit. The story is
   the authored contract for those new choices. Do not refute new in-scope behavior merely because
   no prior OKF node defines it. Refute behavior that contradicts cited existing behavior, expands
   beyond the epic, remains ambiguous, or has no path back to either existing evidence or an
   in-scope epic goal. A citation that resolves to no node is not grounding either.

   **When the surface does not exist yet**, grounding still applies but its evidence differs. On a
   screen being built for the first time the book has no node for it and every AC describes
   something not yet on disk — that is the normal state, not invented scope. An AC is grounded here
   if it traces to the epic's in-scope goal and, where present, the design mockup, spec, or reference
   surface. The story may define details those sources leave open, but it must define them explicitly
   and consistently rather than hand them to the coder.
3. **No hidden decisions.** Catch the semantic open-endedness the structural phrase-list misses:
   "match the legacy behaviour" without saying *what* behaviour, "reasonable defaults", "the usual
   states". If the coder still has a product/UX decision to make, the story isn't ready → **refuted**.
4. **Journey-complete for the surface.** The documented user journeys — the book's `flow` nodes the
   cited surface takes part in — must each be covered by an AC; a component the book says appears
   only in certain contexts must have a presence/absence AC for each context the story touches; an
   interaction whose documented outcome is transient feedback must have an appear-then-disappear AC.
   A missing journey / chrome / transient criterion → **refuted** (this is the exact "caught by luck
   at QA" failure the grounding exists to prevent).

**A defect you cannot point at is not a defect.** Every finding must name the section, criterion or
line of the story it is against, and say what would repair it. If a weakness is real but you cannot
cite where it lives, you have not found it yet — go find it or drop it. The tiebreak is *cite it or
drop it*, not "lean toward refuted": an uncitable refute costs a full rework cycle and comes back as
a different uncitable refute next lap.

**Audit exhaustively, in one lap.** List every defect you can find now, across all four axes. You do
not get a second pass for a defect you could have named here — the next lap only verifies the
repairs to what you list.

## Output

Append an `## Independent Story Audit` section to `{{ workhorse_var('story_dir') }}/audit.md`
recording, per criterion you re-judged: what you checked, the weakness found (or not), and your
verdict.

Then return this exact JSON in your **final response**. The workflow REQUIRES this structure:

```json
{
  "status": "passed" | "failed",
  "findings": [
    {
      "id": "<short stable handle for this defect, e.g. AC3-ungrounded>",
      "kind": "journey" | "chrome" | "transient-feedback" | "grounding",
      "target": "<the AC number, section, or line this is against>",
      "issue": "<what is wrong with it>",
      "repair": "<what would make it right>"
    }
  ],
  "notes": "One line: what you re-verified (upheld), or the shape of the problem (refuted)."
}
```

**Exact requirements**:
- **`findings` is the verdict.** An empty list is a pass, and the workflow reads it that way whatever
  `status` says. Do not return `status: "failed"` with an empty `findings` — that names no defect and
  gives rework nothing to do, so the story is upheld anyway.
- Every finding needs all of `id`, `target`, `issue`, `repair` non-empty. A finding missing any of
  them fails the run rather than reworking, because rework cannot act on it. `id` is a handle you
  choose; nothing parses it — only keep it stable for the same defect across passes.
- `kind` is one of the four axes above and nothing else.
- Do NOT emit `blocked` — you are judging an authored artifact, not running an environment. If the
  story is too thin to judge, that is findings against what is missing, not a blocked status.
- Return the complete JSON exactly as shown, after the markdown audit section.

{% block repo_audit_rules %}{% endblock %}
