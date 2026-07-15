---
agent: agent
---

# Apply {{ repo.name | title }} Story QA Fixes

Apply fixes for a {{ repo.name | title }} story after QA fails. This stage is separate from implementation review fixes and must stay limited to failures documented in the QA report.

**Fix the root cause that makes each failed acceptance criterion true** — within this story's surface that includes a defect spanning the whole surface (state keyed wrong across every field, labels untranslated everywhere, a missing nav/section), not a narrow patch that leaves the criterion only partly met. The QA report's per-criterion findings (the action performed, the old↔new divergence) are your worklist; make each failed criterion observably pass against the source of truth. Genuinely *separate* scope (a different surface) is filed to the backlog, never used to leave this story's criteria unmet. QA reruns after you, so converge across passes rather than half-fixing.

## Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`

Apply QA fixes **only** to the story at the story path above. Do NOT search the repository, git history, or branch state to guess which story to fix, and do NOT substitute a different story. If the story path above is blank or the file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

If `{{ workhorse_var('spec_dir') }}` is blank, derive `<story-name>` from the story folder name in the story path above. The QA report is `{{ workhorse_var('spec_dir') }}/qa.md` and the QA evidence directory is the `qa/` subdirectory beside `story.md`.

### Prior QA Notes

{{ workhorse_var('qa_notes') }}

### Operator Feedback (if provided)

{{ workhorse_var('operator_feedback') }}

If the section above is non-empty, it is mid-flight feedback a human dropped into `{{ workhorse_var('spec_dir') }}/feedback.md` while the run was in progress (QA had already passed). Treat it as **required changes for this pass**, exactly like a QA failure — the Prior QA Notes above may be empty in this case, so the feedback is the work. Apply it within the story's existing scope; QA reruns after you, so do not mark the story QA-passed yourself. If the feedback asks for out-of-scope work, a product decision not present in the story or plan, or a credential/deploy you cannot perform, stop and report a blocker (status `blocked`) rather than expanding scope.

## Required Context

Read:

- `AGENTS.md`
- `{{ instruction_ref("developer") }}`
- the story file
- the parent `epic.md`
- plan artifacts under `docs/specs/<story-name>/`
- `review.md` and its resolution section, if present
- `qa.md`
- story-local QA evidence under `docs/epics/<epic-short-name>/stories/<story-short-name>/qa/`
- relevant instruction files for touched layers, for example `{{ instruction_ref("go") }}`, `{{ instruction_ref("go-testing") }}`, `{{ instruction_ref("go-cli") }}`, `{{ instruction_ref("go-cli-commands") }}`, `{{ instruction_ref("flutter") }}`, `{{ instruction_ref("flutter-architecture") }}`, `{{ instruction_ref("flutter-api") }}`, `{{ instruction_ref("flutter-testing") }}`, or `{{ instruction_ref("pulumi") }}`

## Goal

Resolve the observable failures documented in `qa.md` without adding new story scope.

## Rules

- Fix only QA failures marked `Fail` or required to change the QA result from `Fail` to `Pass`.
- Do not implement optional QA follow-ups unless they are necessary for story acceptance criteria.
- Do not rewrite the plan or broaden product behavior.
- Add or update tests for fixes that affect behavior.
- For Go test changes, load and follow `{{ instruction_ref("go-testing") }}` and relevant {{ template.backend_layer_name | default("Go API") }} or Go CLI instruction files.
- If skills are available, explicitly use the generated Go testing skill before writing or updating Go tests. Do not rely only on automatic path matching.
- Treat `{{ instruction_ref("go-testing") }}` as the canonical source for Go test naming, integration-test shape, fixtures, `require` usage, and context rules. Do not introduce or preserve QA-fix test drift from `go.testing`; if this prompt appears to disagree with `go.testing`, follow `go.testing` and update this prompt.
- Preserve story-local QA evidence; add new evidence only when it helps rerun QA.
- Preserve unrelated user changes.
- Stop instead of guessing if a QA failure requires a product decision, missing fixture, unavailable emulator, or non-MVP behavior.

## Process

1. Create a task list from failed QA scenarios and issues in `qa.md`.
2. Map each failure to the smallest source, fixture, config, or test change needed.
3. Apply fixes one failure at a time.
4. Run targeted verification after each fix.
5. Run final verification for touched layers.
6. Append QA fix notes to `qa.md`.
7. Update the story implementation status.

## Structured Output Requirement

Return this exact JSON object in your **final response**. The workflow REQUIRES this exact structure:

```json
{
  "qa_result": {
    "status": "passed" | "failed" | "blocked",
    "notes": "Summary of QA fixes applied and whether QA now passes or what remains unresolved"
  }
}
```

**Exact requirements**:
- Wrap the result under a `qa_result` key (this is how the workflow captures your output)
- `status` must be one of: `"passed"`, `"failed"`, or `"blocked"` (lowercase, no capital letters)
- `notes` must be a non-empty string summarizing the fixes applied, verification results, and any remaining issues
- Return the complete JSON exactly as shown above
- Include this JSON **after your markdown report** in your final response
- Do NOT deviate from this structure

Example final response (after markdown report):
```json
{
  "qa_result": {
    "status": "passed",
    "notes": "Fixed issue X by modifying Y. Verified with test Z. All prior failures now resolved."
  }
}
```

## QA Fix Resolution Format

Append or update this section in:

`docs/specs/<story-name>/qa.md`

```markdown
## QA Fix Resolution

## Required Skill Files Read

- [list generated skill or instruction files read while applying QA fixes]

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
