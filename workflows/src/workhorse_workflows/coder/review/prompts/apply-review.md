---
agent: agent
---

# Apply The Story's Review Fixes

Apply the required fixes from a story implementation review. This stage must stay limited to review findings.

## Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`

Apply review fixes **only** to the story at the story path above. Do NOT search the repository, git history, or branch state to guess which story to fix, and do NOT substitute a different story. Do not pick a story yourself.

The review report is `{{ workhorse_var('spec_dir') }}/review.md`.

### Review Notes

{{ workhorse_var('review_notes') }}

### Operator Feedback (if provided)

{{ workhorse_var('operator_feedback') }}

If the section above is non-empty, it is mid-flight feedback a human dropped into the run's inbox while the run was in progress. Treat it as **required changes for this pass**, exactly like a review finding — the Review Notes above may be empty in this case, so the feedback is the work. Apply it within the story's existing scope. If it asks for out-of-scope work, a product decision not present in the story or plan, or a credential/deploy you cannot perform, stop and report a blocker (status `blocked`) rather than expanding scope.

## Required Context

Read:

- `AGENTS.md`
- the story file
- the parent `epic.md`
- the plan artifacts under `docs/specs/<story-name>/`
- `review.md`
- the coding standards that govern the files you edit, loaded for those files at the
  moment you edit them

## Goal

Resolve the findings in `review.md` without adding new story scope.

## Rules

- Fix only review findings marked Critical or Major, or explicitly required before QA. Minor findings are suggestions and do not block.
- Do not implement optional suggestions unless they are necessary to satisfy acceptance criteria.
- Do not broaden the plan without stopping to report a blocker.
- Add or update tests for fixes that affect behavior.
- Before changing a layer's tests, load and follow **that layer's testing instruction
  file** from the list above. Load it explicitly; do not rely on automatic path matching.
- Treat that file as the canonical source for the layer's test naming, fixtures,
  integration-test shape and assertion conventions. Fix review findings that identify
  drift from it; where this prompt appears to disagree with it, follow it and say so in
  the summary. A layer with no testing skill in the list above has none in this repo —
  follow the conventions its existing tests already establish.
- Run the narrowest relevant verification after each fix, then final verification for touched layers.
- If a full-layer lint/analyze gate fails only because of pre-existing repository-wide diagnostics outside the story diff, run the narrowest scoped lint/analyze command available for touched files or packages. Mark that review finding resolved for this story when touched files/packages are clean, and document the unrelated full-layer debt in `review.md` without blocking the story.
- Preserve unrelated user changes.

## Process

1. Create a task list from the review findings.
2. Apply fixes one finding at a time.
3. Run targeted tests or checks after each fix.
4. Run final verification for touched layers.
5. Update `review.md` with resolution notes, leaving its `---` frontmatter block intact — it
   carries the `type:` that makes the doc an OKF Concept.
6. Update the story implementation status.

{% block repo_apply_rules %}{% endblock %}

## Review Resolution Format

Append or update this section in:

`docs/specs/<story-name>/review.md`

```markdown
## Resolution

- **Finding 1**: Resolved | Not resolved | Deferred
  - Notes:
  - Verification:

- **Finding 2**: Resolved | Not resolved | Deferred
  - Notes:
  - Verification:
```

## Structured Verdict (machine-checked — required)

Also write a **structured verdict** to `{{ workhorse_var('spec_dir') }}/review-resolution.json`.
A deterministic gate (`ostler edit settle-review`) reads this file, verifies every
artifact and assertion it cites against the filesystem, and ONLY THEN flips the story
status. This is what makes a resolution real: a finding you mark `addressed` whose
cited proof does not exist (or whose assertion does not hold) is **refused** and routed
back for rework — you cannot settle a finding by editing prose alone.

```json
{
  "status": "applied",
  "findings": [
    {
      "id": "Finding 1",
      "disposition": "addressed",
      "artifacts": ["evidence/new-foundation-1280.png", "evidence/new-foundation-390.png"],
      "assertions": [
        {"file": "qa/observations.json", "pointer": "form.headingLabel", "equals": "Foundation area"}
      ]
    },
    {"id": "Finding 2", "disposition": "addressed", "artifacts": ["evidence/new-landing-390.png"]}
  ]
}
```

- `status`: `"applied"` when every required finding is addressed, `"blocked"` if any
  required finding cannot be resolved (e.g. it needs a product decision).
- One entry per required finding, using the **same `id`** the review used (`Finding 1`, …).
- `disposition`: `"addressed"` (you fixed it AND can prove it) or `"blocked"`.
- `artifacts`: paths **relative to the spec dir** to files that prove the fix (e.g. a
  re-captured screenshot). List them only if they exist — the gate checks each one.
- `assertions`: exact-value checks of the form `{file, pointer, equals}` where `pointer`
  is a dotted path into the JSON `file`. Assert the **exact** expected value; never
  broaden an assertion to accept a wrong value to make the gate pass.
- A finding with no machine-checkable proof (e.g. a pure code-rename) may list neither
  `artifacts` nor `assertions` — but a finding the review framed as visual/rendered MUST
  cite the rendered proof, or be `blocked`.

### Per-finding iteration (you may be on a re-apply pass)

The review is settled **one finding at a time**. After each pass the gate writes
`{{ workhorse_var('spec_dir') }}/review-settlement.json` — a ledger with `verified`
(finding ids whose proof now holds — **settled, do not re-open or re-touch**), `open`
(findings whose proof is still missing/wrong — *these are your work this pass*), and
`blocked`. If that file exists, **read it first**:

- Work **only the `open` findings**. Leave the `verified` ones exactly as they are.
- Keep every already-`verified` finding in `review-resolution.json` with its existing
  `artifacts`/`assertions` (the gate re-checks the whole verdict each pass; dropping a
  verified entry or weakening its proof un-settles it).
- A finding you cannot resolve — because it needs a product decision not in the story or
  plan (e.g. *is the new app's "Surface" the correct equivalent of legacy "Foundation
  area"?*) — set to `"disposition": "blocked"`. It escalates to the operator **on its
  own**, without blocking the findings you did settle.

There is **no full re-review** between passes: the deterministic gate is the re-verify,
so closing out the `open` findings (or honestly blocking one) is what advances the loop.

## Story Status

Do **not** hand-edit the story `## Implementation Status` **Status** line — the
`settle-review` gate owns that transition and sets it from your structured verdict
(`Review fixes applied` when verified, `Blocked` for an unresolved finding). You SHOULD
still record verification commands and remaining follow-ups under `## Implementation
Status`; just leave the machine status to the gate.

## Stop Conditions

Stop and report a blocker if:

- a review finding requires a product decision not present in the story or plan
- fixing a finding requires broad replanning
- verification fails for reasons outside story scope
- the review asks for non-MVP behavior

## Commit Identity

Every commit subject ends with `[{{ workhorse_var('story_id') }}]`, after its description.
Every commit also carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
