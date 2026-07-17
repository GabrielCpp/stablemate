---
agent: agent
---

# Rework the story: `{{ workhorse_var('story_slug') }}`

The per-story validator rejected this story. Fix exactly what it flagged, then return control.

## Inputs (authoritative)

- Epic: `{{ workhorse_var('epic') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
- Knowledge record: `{{ workhorse_var('knowledge_record') }}` (the gathered intended↔current gaps for this surface)
- Deterministic validation errors to fix: `{{ workhorse_var('validation_errors') }}`
- Operator feedback to apply (if any): `{{ workhorse_var('operator_feedback') }}`
{%- if workhorse_var('prior_attempts') %}
- **Earlier attempts that already FAILED (do not repeat these approaches):**

{{ workhorse_var('prior_attempts') }}
{%- endif %}

## Task

Address every deterministic validation error above. Common fixes:

- Add a missing/empty required section. The bare-minimum contract needs only **Context** (what &
  why) and **Acceptance Criteria** (observable, user-facing) — do NOT re-add Description, QA,
  Evidence, Verification setup, Dependencies, or Required skills; those are the coder's job now.
- Add the `- **Status**: Not started` line under `## Implementation Status`.
- Make any vague acceptance criterion **observable and user-facing** — what a person using the app
  would see or do (behaviour, visible content, parity with the source of truth), not a DOM selector
  or an implementation detail.
- **Resolve an open question** the validator flagged (`open question / unresolved decision`):
  replace the hedge (`Decision to surface`, `accept, or tune`, `TBD`, `TODO`, `decide whether…`)
  with a made call — `**Decision:** <the choice> — <why>` — and make any interrogative acceptance
  criterion declarative. If the decision truly needs operator/product input, do not leave it in
  the story: return `status: "blocked"` with the question instead.
{% block repo_rework_rules %}{% endblock %}

If **Operator feedback to apply** above is non-empty, the validator and reviewer may have nothing
to flag — the feedback is mid-flight guidance a human dropped into `{{ workhorse_var('story_dir') }}/feedback.md`
while the run was in progress. Treat it as **required changes for this pass**, within the epic's
existing scope. If it asks for out-of-scope work or a product decision not present in the epic/seed,
return `status: "blocked"` with the question rather than expanding scope.

Keep the parts that were already correct. Read `{{ workhorse_var('story_dir') }}/context.md` for
any operator answer.

## Final response (REQUIRED, exact shape)

```json
{
  "write_story_result": {
    "status": "written" | "blocked",
    "notes": "What you fixed, or the blocking question."
  }
}
```
