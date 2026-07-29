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
- **OKF book root**: `{{ workhorse_var('features_dir') }}` — the surface documentation, and the
  grounding source of truth. Read it; never write to it.
{%- endif %}

## Read

- the story file — its **Context** and **Acceptance Criteria** are what you judge
{%- if workhorse_var('features_dir') %}
- **the OKF nodes the story cites** — its `## Context` links them by id (a node id is a
  repo-relative path, optionally `path#anchor`). These are the surface's documented components,
  interactions, and flows: what the story claims to work on, in the book's own words.
{%- endif %}
- the epic's `## Seeds` and `## Stories` sections in `epic.md` — the scope this story claims (the
  seeds it covers and its dependency edges)

## How to audit — try to refute on each axis

1. **Observable + verifiable.** Each AC must be a thing a person *using the running app* could see
   or do — not a DOM selector, not an implementation detail, and not vague ("works correctly",
   "looks right", "is performant"). An un-observable or untestable AC → **refuted**.
2. **Grounded.** Each AC must trace to a cited OKF node (or other cited evidence — a design mockup,
   a spec, a legacy surface). An AC asserting behaviour nothing cited establishes — invented scope —
   → **refuted**. A citation that resolves to no node is not grounding either; the deterministic gate
   catches the dangling id, you catch the AC that leans on it.

   **When the surface does not exist yet**, grounding still applies but its evidence differs. On a
   screen being built for the first time the book has no node for it and every AC describes
   something not yet on disk — that is the normal state, not invented scope. An AC is grounded here
   if it traces to the design mockup, spec, or reference surface the story cites. Refute what traces
   to *nothing* — and "the surface is new" is not itself a warrant.
3. **No hidden decisions.** Catch the semantic open-endedness the structural phrase-list misses:
   "match the legacy behaviour" without saying *what* behaviour, "reasonable defaults", "the usual
   states". If the coder still has a product/UX decision to make, the story isn't ready → **refuted**.
4. **Journey-complete for the surface.** The documented user journeys — the book's `flow` nodes the
   cited surface takes part in — must each be covered by an AC; a component the book says appears
   only in certain contexts must have a presence/absence AC for each context the story touches; an
   interaction whose documented outcome is transient feedback must have an appear-then-disappear AC.
   A missing journey / chrome / transient criterion → **refuted** (this is the exact "caught by luck
   at QA" failure the grounding exists to prevent).

When uncertain whether a weakness is real, **lean toward refuted** — the cost of a wrong refute is
one more bounded rework cycle; the cost of a wrong uphold is the coder building the wrong thing
from a story this mechanism exists to stop.

## Output

Append an `## Independent Story Audit` section to `{{ workhorse_var('story_dir') }}/audit.md`
recording, per criterion you re-judged: what you checked, the weakness found (or not), and your
verdict.

Then return this exact JSON in your **final response**. The workflow REQUIRES this structure:

```json
{
  "audit_result": {
    "status": "passed" | "failed",
    "notes": "If upheld: one line confirming what you independently re-verified. If refuted: the specific weak/ungrounded/missing ACs as a worklist for rework-story (which AC, why, what's needed)."
  }
}
```

**Exact requirements**:
- Wrap the result under an `audit_result` key.
- `status` is `"passed"` only when you independently re-judged the riskiest criteria and could
  **not** refute coder-readiness; otherwise `"failed"`.
- On `"failed"`, `notes` must enumerate the concrete fixes (which AC, why it fails, what it needs)
  so the rework loop can resolve them — not a vague "needs work".
- Do NOT emit `blocked` — you are judging an authored artifact, not running an environment. If the
  story is too thin to judge, that is a **failed** (it must be grounded further), with notes saying so.
- Return the complete JSON exactly as shown, after the markdown audit section.

{% block repo_audit_rules %}{% endblock %}
