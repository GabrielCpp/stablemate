---
agent: agent
---

# {{ repo.name | title }} Regression Suite Fix

The deterministic regression runner just executed the committed user-journey suite for this story
and it did **not** come back clean. Your job is to **fix every failure it reported** — in-branch,
now. There is no distinction between a real regression this story introduced, a stale/flaky spec
that needs hardening, or a genuinely pre-existing bug the suite happened to catch: all three get
fixed the same way. You are not here to classify, exclude, or file the failure to a backlog — that
is not an acceptable outcome. The only way this loop ends is a clean run.

You are **not** re-checking this story's ACs.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- Platform(s) touched: `{{ workhorse_var('platform') }}`  (`web`, `mobile`, or `both`)
- UI service(s) touched: `{{ workhorse_var('service_paths') }}`  (`repo::path` per touched UI service)
- Regression run status: `{{ workhorse_var('regression_run_status') }}`
- Failing tests: `{{ workhorse_var('regression_run_failing_tests') }}`
- Runner notes: `{{ workhorse_var('regression_run_notes') }}`
- Raw run log: `{{ workhorse_var('regression_run_log_path') }}`
- Fix attempt: `{{ workhorse_var('regression_fix_count') }}` of 3

## Required Context

- The platform QA skill(s) for how to bring up the **real** stack and which tool runs the suite:
  web → `{{ instruction_ref("react-router-qa") }}`; mobile → `{{ instruction_ref("flutter-qa") }}`.
- The documented journeys under `docs/features/journeys/<platform>/` and their convention
  (`docs/features/journeys/README.md`). Each journey is one flow.
- `{{ workhorse_var('spec_dir') }}/plan-context.json` (`qa_stack`, `services`) — the stack/fixtures
  the surface needs, and which per-repo/per-service surfaces this story actually changed.
- The committed regression suite for the platform (web: `web/e2e/journeys/*.journey.spec.ts`,
  `make e2e-journeys`; mobile: the Maestro journey flows).
- The raw run log at the path above, and the story diff (`git diff` against the epic base).

## Goal

Make the next deterministic run of the regression suite pass cleanly. Read the failing tests and
log excerpts above, reproduce each failure against the real stack, and fix its root cause.

Use "is this failure on a surface this story touched" and "does it reproduce on the base branch
without this story's diff" only as **diagnostic aids** for deciding *where* the fix belongs (this
story's app code, an unrelated app-code defect the suite caught, or the spec itself), never as a
reason to skip fixing something. Every failure the runner reported gets fixed before you finish.

## Rules

- Real-stack only: do **not** mock the backend, and do **not** convert a journey spec to a mocked
  one to make it pass.
- Never weaken an assertion (e.g. drop a "no server error" check) or deep-link past a broken step
  to force green. A red journey means something is actually broken — find and fix it.
- A failure on a surface this story owns is a defect to fix in the app code.
- A failure on a surface this story did not touch is still fixed here — either the app has a real
  pre-existing bug (fix it) or the spec is stale/flaky (fix the spec: a drifted selector, a race,
  a bad wait). Do not leave it and do not file it to backlog instead of fixing it.
- If the only failure is a selector you can confirm wrong against the running app, fix the
  **selector**. If it's a genuine `5xx` or crash, fix the underlying defect.
- Add or update tests where a fix changes behavior; do not delete or skip a test to clear a failure.
- Preserve unrelated user changes and existing QA evidence.
- Stop and report a blocker only if a fix requires a product decision not present in the story or
  plan, or requires credentials/emulators genuinely unavailable here — not because the fix is hard.

## Process

1. Read the raw run log and failing-test list; group failures by root cause.
2. Reproduce each failure against the real stack.
3. Fix the root cause — app code or spec — one failure at a time.
4. Re-run the affected spec(s) directly (not the full suite — the workflow's deterministic runner
   will do that next) to confirm the fix holds before moving to the next failure.
5. Append a **Regression Fix** section to `{{ workhorse_var('spec_dir') }}/qa.md` summarizing what
   you changed and why, per failure. Append below the existing content and leave the `---`
   frontmatter block intact — it carries the `type:` that makes the doc an OKF Concept.

## Structured Output Requirement

Return this exact JSON object in your **final response** (after a short markdown summary). This
step does **not** decide pass/fail — the workflow re-runs the deterministic suite next and that run
is the only source of truth, so do not include a verdict here.

```json
{
  "regression_fix_result": {
    "notes": "Per-failure summary: what was wrong, what you changed (app code or spec), and how you verified it locally. If a failure could not be fixed, say which one and why."
  }
}
```

- Wrap the result under `regression_fix_result` (this is how the workflow captures your output).
- `notes` must be a non-empty string covering every failure from the inputs above, not just the
  first one.
- Do NOT include a `status` or `qa_result` field — this stage's own claim is not trusted; only the
  next deterministic run is.

## Stop Conditions

Stop and report a blocker in `notes` if:

- a failure requires a product decision not present in the story or plan
- required emulator/services, fixtures, or credentials are unavailable
- a fix would require broad replanning outside this story's surface
