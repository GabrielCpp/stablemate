---
agent: agent
---

# Apply The Story's QA Fixes

Apply fixes for a story after QA fails. This stage is separate from implementation review fixes and must stay limited to failures documented in the QA report.

**Fix the root cause that makes each failed acceptance criterion true** — within this story's surface that includes a defect spanning the whole surface (state keyed wrong across every field, labels untranslated everywhere, a missing nav/section), not a narrow patch that leaves the criterion only partly met. The QA report's per-criterion findings (the action performed, the old↔new divergence) are your worklist; make each failed criterion observably pass against the source of truth. Genuinely *separate* scope (a different surface) is filed to the backlog, never used to leave this story's criteria unmet. QA reruns after you, so converge across passes rather than half-fixing.

## Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`

Apply QA fixes **only** to the story at the story path above. Do NOT search the repository, git history, or branch state to guess which story to fix, and do NOT substitute a different story.

The QA report is `{{ workhorse_var('spec_dir') }}/qa.md` and the QA evidence directory is the `qa/` subdirectory beside `story.md`.

### Prior QA Notes

{{ workhorse_var('qa_notes') }}

### Operator Feedback (if provided)

{{ workhorse_var('operator_feedback') }}

If the section above is non-empty, it is mid-flight feedback a human dropped into the run's inbox while the run was in progress (QA had already passed). Treat it as **required changes for this pass**, exactly like a QA failure — the Prior QA Notes above may be empty in this case, so the feedback is the work. Apply it within the story's existing scope; QA reruns after you, so do not mark the story QA-passed yourself. If the feedback asks for out-of-scope work, a product decision not present in the story or plan, or a credential/deploy you cannot perform, stop and report a blocker (status `blocked`) rather than expanding scope.

If the feedback or QA report names a broad acceptance criterion (`every`, `all`,
`throughout`, `any other`, `each`, `whole app`, or an explicit category list), treat each
named category as required evidence. Fix product/test defects for categories that are
broken, and leave a concrete plan-work item for categories that need new QA assertions;
do not report the criterion resolved from a representative sample that exercised only one
category.

## Required Context

Read:

- `AGENTS.md`
- the story file
- the parent `epic.md`
- plan artifacts under `docs/specs/<story-name>/`
- `review.md` and its resolution section, if present
- `qa.md`
- story-local QA evidence under `docs/epics/<epic-short-name>/stories/<story-short-name>/qa/`
- the coding standards that govern the files you edit, loaded for those files at the
  moment you edit them

## Goal

Resolve the observable failures documented in `qa.md` without adding new story scope.

## Rules

- Fix only QA failures marked `Fail` or required to change the QA result from `Fail` to `Pass`.
- Do not implement optional QA follow-ups unless they are necessary for story acceptance criteria.
- Do not rewrite the plan or broaden product behavior.
- Add or update tests for fixes that affect behavior.
- Before changing a layer's tests, load and follow **that layer's testing instruction
  file** from the list above. Load it explicitly; do not rely on automatic path matching.
- Treat that file as the canonical source for the layer's test naming, fixtures,
  integration-test shape and assertion conventions, and do not let a QA fix drift from
  it; where this prompt appears to disagree with it, follow it and say so in the summary.
  A layer with no testing skill in the list above has none in this repo — follow the
  conventions its existing tests already establish.
- Preserve story-local QA evidence; add new evidence only when it helps rerun QA.
- Never edit `qa-evidence.json`, `qa/qa-run.ndjson` or `qa/run-manifest.json`, and never
  recompute a manifest hash. Those three are the rerun's output, and the manifest hashes are
  what `ostler artifact vet` checks the other two against — refreshing a hash to match an
  edited ledger makes `vet` report clean on a ledger nobody executed, so the tamper detector
  and the evidence it guards fail together and silently. A coverage claim you believe is
  wrong is a finding for the summary, not a record to delete.
- Preserve unrelated user changes.
- Stop instead of guessing if a QA failure requires a product decision, missing fixture, unavailable emulator, or non-MVP behavior.

## Process

1. Create a task list from failed QA scenarios and issues in `qa.md`.
2. Map each failure to the smallest source, fixture, config, or test change needed.
3. Apply fixes one failure at a time.
4. Run targeted verification after each fix.
5. Run final verification for touched layers.
6. Append QA fix notes to `qa.md`.
7. Update the story implementation status — to what your fixes actually leave true, and never
   to a passing verdict. QA reruns after you and the ledger writes the verdict, so a
   hand-written `QA passed` (or an edit to `qa-evidence.json`) only forges the one artifact
   the rerun exists to produce. If you believe the story is done, say so in the JSON below
   and let the rerun agree with you.

## Commit Identity

Every commit carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as footers, spelled exactly so and nowhere else
in the message — not bracketed into the subject — the run record
ties a commit back to its story through them.

## Structured Output Requirement

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}

## QA Fix Resolution Format

Append or update this section in:

`docs/specs/<story-name>/qa.md`

```markdown
## QA Fix Resolution

- **Failure 1**: Resolved | Not resolved | Blocked
  - Notes:
  - Verification:
  - Evidence:

- **Failure 2**: Resolved | Not resolved | Blocked
  - Notes:
  - Verification:
  - Evidence:
```

## Story Status

Update the story `## Implementation Status` section:

- Set **Status** to `QA fixes applied` if all fixable QA failures are resolved and verification passes.
- Set **Status** to `Blocked` if any required QA failure cannot be resolved.
- Add verification commands and remaining follow-ups.

Do not set **Status** to `QA passed`; the QA stage must rerun and make that decision.

## Stop Conditions

Stop and report a blocker if:

- a QA failure requires a product decision not present in the story or plan
- fixing a failure requires broad replanning
- required emulator/services, fixtures, or credentials are unavailable
- verification fails for reasons outside story scope
- the QA report asks for non-MVP behavior
