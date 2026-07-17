---
agent: agent
---

Implement the plan for service `{{ workhorse_var('service_path') }}`. Follow these steps in order.

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`
- Plan file: `{{ workhorse_var('plan_file') }}`
- Service path: `{{ workhorse_var('service_path') }}`
- Service type: `{{ workhorse_var('service_type') }}`
- Verification command: `{{ workhorse_var('verification') }}`

Your CWD is the repo containing the service above. All code changes go in this repo. The service root is `{{ workhorse_var('service_path') }}` within this repo — focus changes there and its dependencies (shared packages in the same repo).

Implement **only** the service-specific plan for this iteration. Do NOT search other repos, git history, or branch state to guess which story to implement, and do NOT substitute a different service.

If the plan file above is blank or does not exist in the spec directory, fall back to `{{ workhorse_var('spec_dir') }}/plan.md`. If the story path is blank or its file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

## Step 1 — Read and Prepare

Before writing any code:

1. Read the story and your **service-specific plan** (from spec dir: `{{ workhorse_var('plan_file') }}`; if multi-service, also skim the root `plan.md` for cross-service contracts). **The story's Acceptance Criteria are the bar — your job is to make ALL of them true** for this service's scope, as a person using the running app would observe them, at parity with the named source of truth. The story is deliberately lean (Context + Acceptance Criteria); it does not list files or steps. **Cover the whole goal**: if satisfying a criterion requires fixing a root cause that spans the surface (e.g. state keyed wrong across every field, labels untranslated everywhere, a missing nav/section), that whole fix is in scope — do not implement a narrow symptom-patch that leaves the criterion only partly met. This may take **several passes**: QA will exercise each criterion against the source of truth and fail anything not actually met, looping you back here. If the story or plan links a surface knowledge record, read it for grounding, but the Acceptance Criteria — not a gap list — define done.
   - **Genuinely separate scope becomes a follow-up, not a narrowing.** Covering the goal means every fix *this* surface needs to meet its criteria. A *different* surface or an unrelated defect you pass through is filed to the backlog (Step 5.3) — never used as an excuse to leave this story's own criteria unmet.
2. Load the coding-standard instruction files the planner resolved for **this** story. The workflow decoded the plan's `plan-context.json` into the list below — read every file in it before writing code:
{% if impl_instruction_paths %}
{%- for path in impl_instruction_paths %}
   - `{{ path }}`
{%- endfor %}
{%- else %}
   - _(The resolved list is empty.)_ Fall back to the plan's **Coding Standards Alignment** (Summary) and **Required Skill Files Read** sections and load every instruction file they name.
{%- endif %}
   - Docs-only work also covers `AGENTS.md` and `docs/CODEX.md`.
3. If the current assistant environment supports skills, use the matching local skills as well — in particular each touched layer's testing skill before writing or updating its tests.
4. **Find each layer's "Verification Commands" section** in its instructions where present — these are the canonical test, codegen, lint, and build commands. The plan's section 6 will reference them.
5. **For multi-layer plans**: read the plan-overview.md first. Note the **implementation order** and **integration contracts**. Implement one layer at a time in the specified order.
6. Track the generated skill or instruction files you read. The implementation notes or story status update must include `Required Skill Files Read`.
7. Check that referenced files exist and dependencies are available.
8. If anything is ambiguous, ask before proceeding.

---

## Step 2 — Build a Task List

Create a small, sequential, testable task list using the task/todo tool available in the current assistant environment. If no task tool is available, maintain the checklist explicitly in your response.

Rules:

- One task per logical unit (one file, one function, one handler).
- After every implementation task, add a **"Run tests"** task.
- If the plan identifies code generation, add a **"Run code generation"** task before the first test that depends on generated output.
- End the task list with a **"Final verification"** task.
- **Multi-layer plans**: Group tasks by layer in the order the plan's **Implementation Order** specifies (typically the API/contract layer before the consumers that depend on it). Complete one layer's tasks — including its final verification — before starting the next. Generic shape:
  ```
  1. [<first layer>]  Run code generation (only if the plan lists any)
  2. [<first layer>]  Implement the change
  3. [<first layer>]  Run tests
  4. [<first layer>]  Final verification
  5. [<next layer>]   Regenerate its client/artifacts (only if the plan lists any)
  6. [<next layer>]   Implement the change
  7. [<next layer>]   Run tests
  8. [<next layer>]   Final verification
  ```

Mark each task `in-progress` when you start and `completed` immediately when it passes — never batch completions.

---

## Step 3 — Implement One Step at a Time

For **each task**:

### 3a. Write the code

- Implement only what this step requires.
- Follow the plan's file paths, function names, and patterns exactly.
- Enforce the target layer's instruction rules for every edit.

### 3b. Write or update tests

- **Every new behavior must have a corresponding test.** Not optional.
- Map each test to the plan's **Given / When / Should** cases.
- Add assertions for: new functions, new branches, new error conditions, new state transitions.
- **For a component that consumes an external contract** (an API payload, another producer's output), derive its test fixtures from a **captured real payload** (a golden file recorded from the real producer), not a hand-authored shape. A fixture you invent can encode the *same wrong assumption* as the code it tests — then both agree and the suite passes green over a real bug. Record the real payload and assert against it.
- Before editing a layer's tests, load and follow that layer's **testing instruction file** from the resolved list in Step 1.2 (e.g. the Go, Flutter, or React testing skill). Treat it as the canonical source for that layer's test naming, fixtures, integration-test shape, and assertion conventions — if this prompt appears to disagree with it, follow the layer's testing skill.
- If skills are available, explicitly use the matching testing skill before writing or updating that layer's tests. Do not rely only on automatic path matching.

### 3c. Run code generation (if applicable)

- If this step modifies files that feed into code generation (an OpenAPI/GraphQL spec, a generated API client, mocks, etc., per the plan's **Code Generation & Build Artifacts** section), run the generation command from the plan's **Verification Commands** now.
- Verify the generated output compiles.

### 3d. Run tests — MANDATORY

- Run the test command from the layer's instruction files → **"Verification Commands"** section where present.
- If no specific command is listed, run the test suite for the affected area.
- **If tests fail, fix the code immediately. Do not move to the next task.**
- Check for regressions in related tests.

### 3e. Check for errors

- Use the available diagnostics, analyzer, compiler, test, lint, or build commands to confirm no compile/type errors remain. If the assistant environment provides an editor diagnostics tool, use it; otherwise rely on the verification commands from the plan.
- Fix all errors before continuing.

### 3f. Mark complete

- Confirm this step matches the plan.
- Update implementation notes or the story status with `Required Skill Files Read` if it is missing or changed.
- Mark the task `completed`.

---

## Step 4 — Final Verification (BLOCKING)

After all implementation tasks are done, run every command from the layer's instruction files → **"Verification Commands"** section in order where present:

1. **Code generation**: Run all codegen commands. Verify output files are up to date. (Skip if plan says "None".)
2. **Tests**: Run the full test command. All must pass.
3. **Lint / Format**: Run the lint/format command. Fix any issues.
4. **Build**: Run the build command. Confirm it succeeds.
5. **Plan review**: Confirm every file in the plan was modified and every success criterion is met.
6. **Standards**: Verify all edits conform to the applicable instruction files.

**Per-service verification**: Run the verification command for this service: `{{ workhorse_var('verification') }}`. This is the canonical build/test/lint command from the repo's agents.yml.

**Generated client code is first-class**: when the plan regenerates an API client (Dart, TypeScript, …), treat the generated package as app code — do **not** hide analyzer/type failures by excluding it. If generated-API analysis fails, fix the generation inputs, the generated package's dependencies, or the regeneration flow until both the app and the generated package pass.

**Story success gate**: Before considering implementation complete, every touched layer must be cleanly formatted, linted/analyzed, tested, and built — using the exact commands from the plan's **Verification Commands** and the layer's instruction files (loaded in Step 1.2). Agent toolkit config or source changes additionally require `farrier --check` to leave generated adapter files current.

**Do not consider the work complete until all required checks pass for every touched layer.**

---

## Step 5 — Run It In A Local Environment (BLOCKING)

Passing unit tests, lint, and build is **necessary but NOT sufficient** — code can compile and test green yet fail to boot, panic on the first request, or render a blank/broken page. **Before you may return `status: "done"`, actually run the changed code in a local environment and exercise the path this story touches**, the same path QA will walk. Shipping code that does not even run locally is the failure this step exists to prevent.

**Run only the layers this story's plan touches** — do not boot a layer the story does not change. The plan determines the scope: run the **"Local run (smoke)"** command the plan's Verification Commands section gives for each touched layer (the planner already worked out which layers are in scope and how to bring them up — a frontend-only story does not start the API; a docs-only story has nothing to run). If the plan's smoke command is missing or insufficient, fall back to the layer's **QA skill** named in the run plan below and the project's local-stack / "operate the local stack" runbook. **Do not invent commands; use the documented ones.** Bound every long-running process with a wall-clock `timeout`.

What "it runs" means per layer — the workflow decoded the plan's touched layers into the run/QA plan below. Run **each** entry; each names the layer's QA skill, which holds the exact local-run command, the tool (curl / Playwright / Maestro / `pulumi preview`), and the observable success signal for that layer:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
- **{{ r.label }}** — bring this layer up and exercise the touched path per `{{ r.qa_skill }}` (and the plan's **Local run (smoke)** command). That skill defines the tool and the success signal; a panic, connection-refused, a boot-time 500, a blank/error page, a stuck loading state, a route that bounces, or an unintended infra `replace`/`delete` is a **defect to FIX now** — not something to discover in QA or hand off.
{%- endfor %}
{%- else %}
- _(No run plan was resolved.)_ Fall back to the plan's `services` (each service's `type` + `path`) + **Local run (smoke)** commands and the touched services' instruction files: bring up each touched service and exercise its path.
{%- endif %}
- **Docs-only** stories (`services` all `type: docs`, or empty) have no runtime to exercise — skip this step and say so in the result notes.
{% if qa_stack and (qa_stack.profile or qa_stack.fixtures) %}
**Use the capable stack — and BUILD what it needs.** The story's **Verification setup** named the stack/profile and the data this surface needs to render with realistic data; the plan carried it forward as `qa_stack`:
{% if qa_stack.profile %}- Stack/profile: {{ qa_stack.profile }}
{% endif %}{% if qa_stack.fixtures %}- Required fixtures/data: {{ qa_stack.fixtures | join('; ') }}
{% endif %}Bring **that** stack up (not whatever thin default is already running) and create the named fixtures/data before you exercise the path. **If the data/seed/migration/stored-procs the surface needs are absent, building or wiring them is IN SCOPE for this story — not a reason to skip.** A surface that renders blank "because there's no data" is the work, not a wall: seed it, add the migration, point at the capable profile, then exercise it. Do not walk away from a surface just because the story body didn't spell out the fixture.
{% endif %}
1. **Walk the actual story path end-to-end at least once** (e.g. sign in → reach the feature → exercise it), the way QA will. A runtime error, a route that bounces, a 500, a missing element, or a stuck loading state is a **defect to FIX now** — not something to discover in QA or hand off.
2. **Capture a short proof** the run really happened: a server boot log line plus the endpoint's response, or a screenshot of the rendered route. Save it beside the story (e.g. its `qa/` or spec dir). Do not assert "it runs" without evidence.
3. **If exercising the path reveals a *separate* broken surface** that is out of this story's scope (e.g. a blank screen on a neighboring route you happened to pass through), do not absorb it and do not ignore it — **file it to the backlog** by appending an entry to `{{ workhorse_var('spec_dir') }}/backlog-items.json` (`{"id": "<kebab-id>", "description": "<one line>", "section": "## <domain>"}`; a deterministic node drains it). This is only for *separate* scope: a missing seed/fixture/migration for *this* story's surface is in-scope to BUILD (above), never filed.

If a touched layer's local environment **genuinely cannot be brought up** here (no Docker, no emulator, an operator-only dependency), do **not** report `done` — return `status: "blocked"` naming exactly what was missing. "Unit tests passed but I could not run it" is **`blocked`, never `done`.** `blocked` is reserved for an **operator-only foundation** (no Docker / a real credential / a real deploy). A **missing fixture, seed, migration, stored procedure, or data row** the surface needs is *not* `blocked` — it is in-scope to build (above); build it and exercise the surface.

{% block repo_impl_rules %}{% endblock %}

---

## Rules

**Never do this:**

- Skip running tests after an implementation step.
- Skip code generation when the plan identifies generated files.
- Mark a task complete before its tests pass.
- Continue with compile errors or failing tests.
- **Report `done` when you never ran the code in a local environment.** Green unit tests are not proof the code runs.
- **Report `done` with lint failing.** Run the service's `make lint` (or its configured lint command) and leave it clean — a deterministic lint gate re-runs it and routes any failure back to rework, so a dirty tree does not actually finish the story faster.
- Apply the wrong layer's instruction set.
- Start implementing a consumer layer before the contract/API layer it depends on passes verification.

**Always do this:**

- Run tests after every implementation step — not just at the end.
- **Run `make lint` in the service directory before declaring `done`** (where it exists) and fix every finding — formatting, unused imports, and any accessibility findings for UI work (missing labels/roles, unnamed controls). Follow the loaded accessibility skill for UI surfaces.
- Run code generation before testing when generated files are involved.
- **Bring up the local stack and exercise the touched story path (Step 5) before declaring `done`.**
- Use the exact commands from the layer's instruction files → **"Verification Commands"** section where present.
- Fix errors immediately — never defer them.
- Re-read the plan section before coding each step.
- For multi-layer stories, implement layers in the order specified by the plan's **Implementation Order** (typically the API/contract layer before the consumers that depend on it) and verify each before moving on.

## Machine-Readable Result (required)

After implementing the story and running verification, return this exact JSON object as the LAST thing in your final response. The workflow captures it under the `impl_result` key — without it the node fails to parse and is retried:

```json
{"impl_result": {"status": "done|blocked", "notes": "<what you implemented and verified, or what blocked you>"}}
```

- `status`: `"done"` only when the implementation is complete, verification passed, **and the code was run in a local environment with the touched story path exercised (Step 5)**. Use `"blocked"` if you could not complete it or could not run it locally.
- `notes`: a brief summary of what was implemented and verified, **including how you ran it locally and what you observed** (or the blocker).
