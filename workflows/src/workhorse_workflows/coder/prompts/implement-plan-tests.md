---
agent: agent
---

Write the **failing tests** for service `{{ workhorse_var('service_path') }}` — tests only, no production code. This is the first half of a two-turn TDD split: you translate the plan's Test Scenarios into tests that fail because the behavior does not exist yet; a separate turn will make them pass.

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`
- Plan file: `{{ workhorse_var('plan_file') }}`
- Service path: `{{ workhorse_var('service_path') }}`
- Service type: `{{ workhorse_var('service_type') }}`
- Test command the gate will run: `{{ workhorse_var('test_command') }}`

Your CWD is the repo containing the service above. The service root is `{{ workhorse_var('service_path') }}` within this repo. If the plan file above is blank or does not exist in the spec directory, fall back to `{{ workhorse_var('spec_dir') }}/plan.md`. If the story path is blank or its file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

{% if operator_context %}
## Operator answer (authoritative ground truth)

You raised a block on this story and an operator answered it. Treat the following as fact: it
overrides any earlier assumption in the story, the plan or the code. Do **not** re-derive it,
second-guess it, or raise the same block again — it has been answered.

{{ workhorse_var('operator_context') }}
{% endif %}

{% if gate_feedback %}
## Rework — the red gate rejected the previous attempt

> {{ workhorse_var('gate_feedback') }}

What each rejection means:

- `all_green` — the suite passed with the behavior still unimplemented. The tests exercise nothing missing: they assert on existing behavior, mock away the thing under test, or never call the new code path. Rewrite them to genuinely depend on the missing behavior.
- `impure` — the diff contained **production code**: a source, markup, style, SQL or terraform file that is not test code. Revert every listed file and express the setup inside test files instead. Fixtures, data files, docs and config are *not* impure — only code the code turn owes is.
- `no_tests` — you wrote no test file. Write the tests; if something genuinely blocks you, return `status: "blocked"` naming it instead of doing nothing.
- `unattributed_red` — the suite failed, but no reported failure named any file you wrote: the red belongs to something already broken, not to your tests. Make the scenarios actually run (a skipped, uncollected or never-imported test proves nothing) and confirm your own test names appear in the failure output.
{% endif %}

## Step 1 — Read and Prepare

1. Read the story and your **service-specific plan** (from the spec dir: `{{ workhorse_var('plan_file') }}`). The plan's **Test Scenarios** section maps each Acceptance Criterion to the test(s) that will prove it, with a level (unit / component / integration). That mapping is your work order. **Exclude scenarios marked as QA-only or end-to-end** — browser/device-driven journeys belong to the QA lane, not this suite.
2. Load the coding-standard instruction files the planner resolved for **this** story — read every file in the list before writing tests, and follow each touched layer's **testing** instruction file for naming, fixtures, and assertion conventions:
{% if impl_instruction_paths %}
{%- for path in impl_instruction_paths %}
   - `{{ path }}`
{%- endfor %}
{%- else %}
   - _(The resolved list is empty.)_ Fall back to the plan's **Required Skill Files Read** section and load every instruction file it names.
{%- endif %}
3. Read the existing test suite around the service so new tests land in the right files, follow the local naming signature, and reuse the established fixtures and helpers.

## Step 2 — Write the Tests

For each Test Scenario in scope:

- Write it at the level the plan assigned. Prefer the smallest level that can observe the criterion; extend an existing integration test rather than duplicating one where the plan says so.
- Assert on the **behavior the Acceptance Criterion describes**, not on implementation details — the code turn must be free to implement the plan's design without rewriting your assertions.
- **The test must fail because the behavior is missing** — a compile error in the test itself, an import typo, or a broken fixture is not a meaningful red. Where the language allows, reference the planned entry points so the failure is an assertion failure or a missing-symbol error at the planned seam, not noise.
- For a component that consumes an external contract (an API payload, another producer's output), derive fixtures from a **captured real payload** where one exists in the repo, not a hand-authored shape.

## Step 3 — Observe Red

Run the test command above (or, if it is blank, the touched area's test command from the layer's instruction files). **Confirm the new tests fail and the failures are the meaningful kind** — an assertion about the missing behavior, not a setup error. Pre-existing tests must still pass; if your additions broke an unrelated test's collection or build, fix the test code until only the intended failures remain.

A deterministic gate re-runs this command after your turn and inspects the diff. It loops the work back to you when the suite exits green, when the diff contains production code, when no test file was written, or when the failures it sees name none of your files — so the fastest path through is a pure diff that is red **on your tests**.

## Rules

**Never do this:**

- Create or edit **any production code file** — no source, no markup, no styles, no SQL, no terraform, no generated code. Fixtures, test data and test-local config are yours; the implementation is the code turn's.
- Write a test that passes against the current code. Red is the deliverable.
- Stub or mock the very behavior under test so the test can pass without it.
- Delete or weaken existing tests to make room.
- Hand-edit the story's `status:` frontmatter or its `## Implementation Status` **Status** line — later gates own those transitions.

**Always do this:**

- Cover every in-scope Test Scenario from the plan — the reviewer audits AC coverage against this suite.
- Follow the layer's testing instruction file for file naming: the gate recognizes test files by the repo's configured signatures, and a test written to an unrecognized path is judged as production code.
- Run the suite and observe the red yourself before finishing.

## Machine-Readable Result (required)

Return this exact JSON object as the LAST thing in your final response — without it the node fails to parse and is retried:

```json
{"status": "done|blocked", "notes": "<the scenarios covered and the red you observed, or what blocked you>"}
```

- `status`: `"done"` when the tests are written and you observed them fail for the right reason. `"blocked"` when something outside your control prevents writing them.
- `notes`: which Test Scenarios each test covers and what the failing run showed, or the blocker.
