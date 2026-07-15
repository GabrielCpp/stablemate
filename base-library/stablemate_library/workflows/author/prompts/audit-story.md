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
- Knowledge record: `{{ workhorse_var('knowledge_record') }}` — the grounding source of truth.
{%- if workhorse_var('features_dir') %}
- Feature-doc root: `{{ workhorse_var('features_dir') }}` — the documented user journeys.
{%- endif %}

## Read

- the story file — its **Context** and **Acceptance Criteria** are what you judge
- the surface **knowledge record** (components, gaps, `journeys[]`, `chromeContext`, `feedbackKind`)
- the epic's `## Seeds` and `## Stories` sections in `epic.md` — the scope this story claims (the
  seeds it covers and its dependency edges)
{%- if workhorse_var('features_dir') %}
- this surface's feature doc / journey under `{{ workhorse_var('features_dir') }}`
{%- endif %}

## How to audit — try to refute on each axis

1. **Observable + verifiable.** Each AC must be a thing a person *using the running app* could see
   or do — not a DOM selector, not an implementation detail, and not vague ("works correctly",
   "looks right", "is performant"). An un-observable or untestable AC → **refuted**.
2. **Grounded.** Each AC must trace to a component/gap in the knowledge record (or cited evidence).
   An AC asserting behaviour the record does not establish — invented scope — → **refuted**.
3. **No hidden decisions.** Catch the semantic open-endedness the structural phrase-list misses:
   "match the legacy behaviour" without saying *what* behaviour, "reasonable defaults", "the usual
   states". If the coder still has a product/UX decision to make, the story isn't ready → **refuted**.
4. **Journey-complete for the surface.** The documented user journey(s) in the record's `journeys[]`
   must each be covered by an AC; every component with `chromeContext` must have a presence/absence
   AC for each context; every `feedbackKind: "transient"` must have an appear-then-disappear AC. A
   missing journey / chrome / transient criterion → **refuted** (this is the exact "caught by luck
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
