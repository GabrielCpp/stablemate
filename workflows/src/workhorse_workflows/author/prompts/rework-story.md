---
agent: agent
---

# Rework the story: `{{ workhorse_var('story_slug') }}`

This story came back for repair. Fix exactly what was flagged, then return control.

The flags below come from one of two places, and they read differently. The deterministic validator
emits plain error lines. The independent audit emits **findings**, one per line, shaped
`<id> [<kind>] <target>: <issue>. Repair: <repair>` — address each one at the `target` it names, and
do not treat the list as a licence to rewrite the rest of the story. The `id` is how the next audit
recognises the same defect, so a finding you leave unrepaired will come straight back under its own
name; if you believe a finding is wrong, say which id and why in `notes` rather than ignoring it.

## Inputs (authoritative)

- Epic: `{{ workhorse_var('epic') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
{%- if workhorse_var('mockup_path') %}
- Design mockup: `{{ workhorse_var('mockup_path') }}` — keep the story's Context linked to this visual
  source of truth when the validation issue does not supersede it.
{%- endif %}
{%- if workhorse_var('features_dir') %}
- **OKF book root**: `{{ workhorse_var('features_dir') }}` — the existing surface documentation the
  story cites by node id from its `## Context`. Read it; never write to it, and do not inspect the
  app or source code to discover replacement nodes.
{%- endif %}
- Validation errors or audit findings to fix: `{{ workhorse_var('validation_errors') }}`
- Operator feedback to apply (if any): `{{ workhorse_var('operator_feedback') }}`
{%- if workhorse_var('prior_attempts') %}
- **Earlier attempts that already FAILED (do not repeat these approaches):**

{{ workhorse_var('prior_attempts') }}
{%- endif %}

## Task

Address every error or finding above. Common fixes:

- Add a missing/empty required section. The bare-minimum contract needs only **Context** (what &
  why) and **Acceptance Criteria** (observable, user-facing) — do NOT re-add Description, QA,
  Evidence, Verification setup, or Required skills; those are the coder's job now. Leave
  `## Dependencies` exactly as you found it — it is the story DAG, not prose to rewrite.
- Add the `- **Status**: Not started` line under `## Implementation Status`.
- Make any vague acceptance criterion **observable and user-facing** — what a person using the app
  would see or do (behaviour, visible content, parity with the source of truth), not a DOM selector
  or an implementation detail.
- **Resolve an open question** the validator flagged (`open question / unresolved decision`):
  replace the hedge (`Decision to surface`, `accept, or tune`, `TBD`, `TODO`, `decide whether…`)
  with a made call — `**Decision:** <the choice> — <why>` — and make any interrogative acceptance
  criterion declarative. When the epic puts the behavior in scope, make the concrete choice in the
  Acceptance Criteria even if no prior OKF node specifies the detail. Do not block merely because
  the existing OKF book is silent. Block only if the choice would broaden scope, contradict an
  existing source, or resolve a genuine conflict the supplied evidence cannot settle.
{% block repo_rework_rules %}{% endblock %}

If **Operator feedback to apply** above is non-empty, the validator and reviewer may have nothing
to flag — the feedback is mid-flight guidance a human dropped into the run's inbox while the run
was in progress. Treat it as **required changes for this pass**, within the epic's existing scope.
If it asks for out-of-scope work or a product decision not present in the epic/seed, return
`status: "blocked"` with the question rather than expanding scope.

Keep the parts that were already correct. Read `{{ workhorse_var('story_dir') }}/context.md` for
any operator answer.

## Final response (REQUIRED, exact shape)

```json
{
  "status": "written" | "blocked",
  "notes": "What you fixed, or the blocking question."
}
```
