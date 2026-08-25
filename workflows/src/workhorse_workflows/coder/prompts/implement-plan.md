---
agent: agent
---

Implement the plan for service `{{ workhorse_var('service_path') }}`. Follow these steps in order.

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`
- Service path: `{{ workhorse_var('service_path') }}`
- Service type: `{{ workhorse_var('service_type') }}`
- Verification command: `{{ workhorse_var('verification') }}`
- Gates that run after this turn: {{ workhorse_var('gates') or '(nothing declared)' }}
- Tests, as this repo declares them: `{{ workhorse_var('tdd') or 'off' }}`

The gate line above is what the workflow will actually run once you report `done`, taken
from this service's declaration — not a guess, and not a list to add to. Run those commands
yourself before finishing and leave them green; a red one comes straight back to you as a
repair turn with its output attached. Where it says nothing is declared, no gate will run
and there is no command for you to invent.

{% if workhorse_var('tdd') == 'required' %}
**This service requires tests, so the failing test is your first edit.** Write the test that
fails for the reason the story is not yet true, watch it fail, then make it pass. Report the
test files you wrote in `tests_added`; a turn that reports none, or names a file the diff
does not contain, comes back as a repair turn.
{% elif workhorse_var('tdd') == 'encouraged' %}
**This service encourages tests.** Where the change has observable behaviour, lead with the
failing test. Report what you wrote in `tests_added` — a miss is recorded, not punished.
{% endif %}

Your CWD is the repo containing the service above. All code changes go in this repo. The service root is `{{ workhorse_var('service_path') }}` within this repo — focus changes there and its dependencies (shared packages in the same repo).

Implement **only** the plan you were handed for this iteration. Do NOT search other repos, git history, or branch state to guess which story to implement, and do NOT substitute a different service.

If the story path is blank or its file does not exist, stop and report that the workflow did not provide a usable story path — do not pick a story yourself.

{% if operator_context %}
## Operator answer (authoritative ground truth)

You raised a block on this story and an operator answered it. Treat the following as fact: it
overrides any earlier assumption in the story, the plan or the code. Do **not** re-derive it,
second-guess it, or raise the same block again — it has been answered.

{{ workhorse_var('operator_context') }}
{% endif %}

## Step 1 — Read and Prepare

Before writing any code:

1. Read the story{% if plan_text %} — your plan is inlined under **"The Plan"** at the end of this prompt; it is already in front of you, so do not spend a turn reading it from disk{% else %}, and your plan: `{{ workhorse_var('spec_dir') }}/{{ workhorse_var('plan_file') or 'plan.md' }}`{% endif %}. **The story's Acceptance Criteria are the bar — your job is to make ALL of them true**, as a person using the running app would observe them, at parity with the named source of truth. **Cover the whole goal**: if satisfying a criterion requires fixing a root cause that spans the surface (e.g. state keyed wrong across every field, labels untranslated everywhere, a missing nav/section), that whole fix is in scope — do not implement a narrow symptom-patch that leaves the criterion only partly met. This may take **several passes**: QA will exercise each criterion against the source of truth and fail anything not actually met, looping you back here. The story's `## Context` links the documentation it is grounded in; read those links for grounding, but the Acceptance Criteria — not the docs — define done.
   - A *different* surface or an unrelated defect you pass through is filed to the backlog (Step 5.3) as a follow-up — never absorbed into this story, and never an excuse to leave this story's own criteria unmet.
2. Hold this story's coding standards — the workflow derived them from the layers the plan declares.
{%- if impl_instructions %} **Their full text is inlined under "Coding Standards (inlined)" at the end of this prompt — it is already in front of you, so do not spend turns re-reading those files.** A standard listed there without an inlined body is the exception: read that path yourself before writing code.
{%- elif impl_instruction_paths %} Read every one of these before writing code:
{%- for path in impl_instruction_paths %}
   - `{{ path }}`
{%- endfor %}
{%- else %}
   - _(The resolved list is empty.)_ Fall back to the standards the plan's **Approach** and **Changes** sections cite by name, and load each one.
{%- endif %}
   - Docs-only work also covers `AGENTS.md` and `docs/CODEX.md`.
3. If the current assistant environment supports skills, use the matching local skills as well — in particular each touched layer's testing skill before writing or updating its tests.
4. **Find each layer's "Verification Commands" section** in its instructions where present — these are the canonical test, codegen, lint, and build commands. The plan's **Verification Commands** section references them.
5. **For multi-layer plans**: note the plan's **implementation order** and **integration contracts**{% if root_plan_text %} (the cross-service contracts are inlined under **"Cross-service contracts"** at the end of this prompt){% endif %}. Implement one layer at a time in the specified order.
6. Check that referenced files exist and dependencies are available.
7. **Search before you build.** List the concrete units the plan says it will create — endpoints, service methods, models, components, screens, validators, formatters, any "helper" or "util" it names — and search the affected repos for each one before writing it. Match on **behaviour, not name**: the existing version is often called something else, and shared utility trees are where reinvention concentrates. Reuse or extend what you find; where you deliberately do not, say why in the implementation notes. A capability rebuilt beside the one that already does it is the single most common defect this stage produces, and it is cheapest to catch here — you are about to read this code anyway.
8. If anything is ambiguous, ask before proceeding.

---

## Step 2 — Build a Task List

Create a small, sequential, testable task list using the task/todo tool available in the current assistant environment. If no task tool is available, maintain the checklist explicitly in your response.

Rules:

- One task per coherent unit of *behaviour* — an endpoint, a service method with its ports, a screen. A task may span several files; a file is not a task.
- One **"Run tests"** task per layer, after that layer's implementation tasks — not one after every task.
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

Mark each task `in-progress` when you start it and `completed` once its layer's checks pass — never before the check that covers it has run.

### State your exit conditions before you start

The Acceptance Criteria are given — nothing here asks you to invent the bar. What only you
can state is the concrete, checkable evidence *this turn* will leave behind, and the
workflow holds you to it: with the task list in front of you and before the first edit,
write down what "done" will look like — you will return it as `exit_conditions` in the
result below, and the workflow runs and diffs it against what actually happened:

- `criteria` — the story's acceptance criteria this turn intends to satisfy, in the story's
  own words. Carried forward to review and QA as the thing to check first.
- `commands` — the commands you expect to be green when you finish, beyond the gates in
  **Provided Inputs** (those are run for you either way). The workflow runs each one and waits
  for it to exit; a red one comes back as a repair turn quoting your own promise. **Every
  command here must terminate on its own.** A process that runs until it is stopped — a
  server, a watcher, a tail — can never be green: the gate waits out its timeout, calls the
  promise broken, and bills a repair lap against finished work. Promise the terminating
  command that proves the same thing instead. **Each entry is the command and nothing
  else** — the exact string a shell is handed. Not the command with its outcome written
  beside it, not a note about which environment it needs: that belongs in `notes`, and a
  shell handed it exits non-zero no matter how finished the work is.
- `files` — the files you expect to have touched. One missing from the diff comes back the
  same way.

Promise what you mean to do, not everything you could imagine doing: an unmet promise costs
a whole repair lap, and a turn that promises nothing simply forfeits the check. Revise the
list as you learn — what you return at the end is what you are held to.

---

## Step 3 — Implement in Batches, Verify per Layer

Spend your turns on edits, not ceremony: **batch independent file writes and edits into the
same response wherever your tools allow.** A turn that writes one small file and stops is
latency spent on nothing — when the plan names five files whose contents you already know,
write all five in one turn. Serialize only where a later edit genuinely depends on an
earlier command's output (generated code, a failing test's message).

### 3a. Write the code and its tests, together

- Work the task list in order; implement each task fully — production code **and its tests
  in the same pass**. **Every new behavior must have a corresponding test.** Not optional.
- Follow the plan's file paths, function names, and patterns exactly, and enforce the
  target layer's instruction rules for every edit.
- Map each test to the plan's **Given / When / Should** cases; add assertions for new
  functions, branches, error conditions, and state transitions.
- **For a component that consumes an external contract** (an API payload, another producer's output), derive its test fixtures from a **captured real payload** (a golden file recorded from the real producer), not a hand-authored shape. A fixture you invent can encode the *same wrong assumption* as the code it tests — then both agree and the suite passes green over a real bug. Record the real payload and assert against it.
- Before editing a layer's tests, follow that layer's **testing instruction file** from the standards resolved in Step 1.2 — that set is the whole set; a layer missing from it
  has no testing skill in this repo. Treat it as the canonical source for that layer's test naming, fixtures, integration-test shape, and assertion conventions — if this prompt appears to disagree with it, follow the layer's testing skill.
- If skills are available, explicitly use the matching testing skill before writing or updating that layer's tests. Do not rely only on automatic path matching.

### 3b. Run code generation when its inputs change

- When your edits modify files that feed into code generation (an OpenAPI/GraphQL spec, a generated API client, mocks, etc., per the plan's **Code Generation & Build Artifacts** section), run the generation command from the plan's **Verification Commands** before writing code that depends on the generated output, and verify it compiles.

### 3c. Verify once per layer

- When a layer's implementation tasks are done, run its verification **once, as a batch**:
  the gate commands from **Provided Inputs** plus the test command from the layer's
  instruction files → **"Verification Commands"** section where present. Do **not** re-run
  the full gate set after every task — the per-task loop is where runs go to spend their
  wall clock.
- **If a check fails, fix the code immediately and re-run what failed**, then the batch
  once more; watch for regressions in related tests. Do not start the next layer with this
  one red.
- Use the available diagnostics/analyzer output to confirm no compile/type errors remain
  before calling the layer done.

### 3d. Mark complete

- Confirm the finished tasks match the plan, then mark them `completed` — marking several
  at once right after a green verify is fine; claiming one before its check ran is not.

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

**Generated client code is first-class**: when the plan regenerates an API client in any language, treat the generated package as app code — do **not** hide analyzer/type failures by excluding it. If generated-API analysis fails, fix the generation inputs, the generated package's dependencies, or the regeneration flow until both the app and the generated package pass.

**Story success gate**: Before considering implementation complete, every touched layer must be cleanly formatted, linted/analyzed, tested, and built — using the exact commands from the plan's **Verification Commands** and the layer's instruction files (loaded in Step 1.2). Agent toolkit config or source changes additionally require `farrier --check` to leave generated adapter files current.

**Do not consider the work complete until all required checks pass for every touched layer.**

---

## Step 5 — Run It In A Local Environment (BLOCKING)

Passing unit tests, lint, and build is **necessary but NOT sufficient** — code can compile and test green yet fail to boot, panic on the first request, or render a blank/broken page. **Before you may return `status: "done"`, actually run the changed code in a local environment and exercise the path this story touches**, the same path QA will walk. Shipping code that does not even run locally is the failure this step exists to prevent.

**Run only the layers this story's plan touches** — do not boot a layer the story does not change. The plan determines the scope: run the **"Local run (smoke)"** command the plan's Verification Commands section gives for each touched layer (the planner already worked out which layers are in scope and how to bring them up — a frontend-only story does not start the API; a docs-only story has nothing to run). If the plan's smoke command is missing or insufficient, fall back to the layer's **QA skill** named in the run plan below and the project's local-stack / "operate the local stack" runbook. **Do not invent commands; use the documented ones.** Bound every long-running process with a wall-clock `timeout`.

What "it runs" means per layer — the workflow decoded the plan's touched layers into the run/QA plan below. Run **each** entry; each names the layer's QA skill, which holds the exact local-run command, the driver that exercises it, and the observable success signal for that layer:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
- **{{ r.label }}** — bring this layer up and exercise the touched path per `{{ r.qa_skill }}` (and the plan's **Local run (smoke)** command). That skill defines the tool and the success signal; a panic, connection-refused, a boot-time 500, a blank/error page, a stuck loading state, a route that bounces, or an unintended infra `replace`/`delete` is a **defect to FIX now** — not something to discover in QA or hand off.
{%- endfor %}
{%- else %}
- _(No run plan was resolved.)_ Fall back to the plan's `services` (each service's `type` + `path`) + **Local run (smoke)** commands and the touched services' instruction files: bring up each touched service and exercise its path.
{%- endif %}
- **Docs-only** stories (`services` all `type: docs`, or empty) have no runtime to exercise — skip this step and say so in the result notes.
{% if verification_setup and (verification_setup.profile or verification_setup.fixtures) %}
**Use the capable stack — and BUILD what it needs.** The story's **Verification setup** named the stack/profile and the data this surface needs to render with realistic data; the plan carried it forward as `verification_setup`:
{% if verification_setup.profile %}- Stack/profile: {{ verification_setup.profile }}
{% endif %}{% if verification_setup.fixtures %}- Required fixtures/data: {{ verification_setup.fixtures | join('; ') }}
{% endif %}Bring **that** stack up (not whatever thin default is already running) and create the named fixtures/data before you exercise the path. **If the data/seed/migration/stored-procs the surface needs are absent, building or wiring them is IN SCOPE for this story — not a reason to skip.** A surface that renders blank "because there's no data" is the work, not a wall: seed it, add the migration, point at the capable profile, then exercise it. Do not walk away from a surface just because the story body didn't spell out the fixture. 
{% endif %}
**Record the durable, code-independent part of the bring-up in the book's `runbook` node** (`docs/features/<service>/ops/qa-stack.md` — containers, emulators, the datastore and its baseline seed, as its `kind: prepare` and `kind: seed` steps) so QA's `ensure_stack` step reuses exactly what you ran — never leave a stack backgrounded in your shell for QA to inherit; a process the workflow does not own dies at node teardown. `ostler scaffold runbook qa-stack --service <service>` writes the node if this repo has none yet, `ostler qa stack up` runs exactly what the workflow will, and `ostler doctor` tells you whether it reads the way you meant. This is **not** gated on the story naming a verification setup: a story that stands a new service up and does not record it leaves QA with nothing to test against, which is a whole run's budget spent rediscovering that. **Do not give the runbook a `kind: service` step for a service pinned to this story's own working-tree source** (an API/dev server QA must run against *this* branch's code, not an adopted image) — the health probe is always a `GET` expecting `200`–`399`, so a POST-only or GET-less surface can never satisfy it there. That service belongs in the QA plan's own `background()` step instead (`ready_cmd`/`ready_contains` when the readiness route is not a plain `GET`), which the QA plan authoring skill covers — record its bring-up command in the story's QA-plan notes, not in the runbook.
1. **Walk the actual story path end-to-end at least once** (e.g. sign in → reach the feature → exercise it), the way QA will. A runtime error, a route that bounces, a 500, a missing element, or a stuck loading state is a **defect to FIX now** — not something to discover in QA or hand off.
2. **Capture a short proof** the run really happened: a server boot log line plus the endpoint's response, or a screenshot of the rendered route. Save it beside the story (e.g. its `qa/` or spec dir). Do not assert "it runs" without evidence.
3. **If exercising the path reveals a *separate* broken surface** that is out of this story's scope (e.g. a blank screen on a neighboring route you happened to pass through), do not absorb it and do not ignore it — **file it to the backlog** by appending an entry to `{{ workhorse_var('spec_dir') }}/backlog-items.json` (`{"id": "<kebab-id>", "description": "<one line>", "section": "## <domain>"}`; a deterministic node drains it). This is only for *separate* scope: a missing seed/fixture/migration for *this* story's surface is in-scope to BUILD (above), never filed.

If a touched layer's local environment **genuinely cannot be brought up** here (no Docker, no emulator, an operator-only dependency), do **not** report `done` — return `status: "blocked"` naming exactly what was missing. "Unit tests passed but I could not run it" is **`blocked`, never `done`.** `blocked` is reserved for an **operator-only foundation** (no Docker / a real credential / a real deploy). A **missing fixture, seed, migration, stored procedure, or data row** the surface needs is *not* `blocked` — it is in-scope to build (above); build it and exercise the surface.

{% block repo_impl_rules %}{% endblock %}

---

## Rules

**Never do this:**

- Skip a layer's test run before moving to the next layer.
- Skip code generation when the plan identifies generated files.
- Mark a task complete before the check that covers it has passed.
- Continue with compile errors or failing tests.
- **Report `done` when you never ran the code in a local environment.** Green unit tests are not proof the code runs.
- **Report `done` with a declared gate red.** The workflow re-runs every gate in **Provided Inputs** and routes a failure straight back to you, so leaving one dirty does not finish the story faster.
- **Hand-edit the story's `status:` frontmatter or its `## Implementation Status` **Status** line.** See "Story Status" below.
- Apply the wrong layer's instruction set.
- Start implementing a consumer layer before the contract/API layer it depends on passes verification.

**Always do this:**

- Run each layer's tests when its implementation tasks are done — not only once at the very end of a multi-layer story.
- Batch independent file writes into one turn; serialize only on genuine dependencies.
- **Run every gate command from Provided Inputs in the service directory before declaring `done`** and fix every finding — formatting, unused imports, and any accessibility findings for UI work (missing labels/roles, unnamed controls). Follow the loaded accessibility skill for UI surfaces.
- Run code generation before testing when generated files are involved.
- **Bring up the local stack and exercise the touched story path (Step 5) before declaring `done`.**
- Use the exact commands from the layer's instruction files → **"Verification Commands"** section where present.
- Fix errors immediately — never defer them.
- Re-read the plan section before coding each step.
- For multi-layer stories, implement layers in the order specified by the plan's **Implementation Order** (typically the API/contract layer before the consumers that depend on it) and verify each before moving on.

## Story Status

Do **not** hand-edit the story's `status:` frontmatter or its `## Implementation Status`
**Status** line. Later gates own those transitions and set them from a structured verdict —
`Reviewed` from review, `QA passed` only from a QA run the workflow itself performed. You
have not reached those stages, so any status you write is a claim about work that has not
happened yet.

This matters beyond tidiness: the queue reads that line. `QA passed`, `done`, `merged` and
`complete` all mark the story finished, so a status written here makes the story invisible
to story selection — if the run later gives up, crashes, or sets the epic aside, the story
stays "passed" forever without QA ever having verified it.

Re-verifying a previously failed story is still your job when the plan says so, and so is
recording what you ran. Put that under `## Implementation Status` as prose and leave the
**Status** line to the gate.

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `feat` when the story adds behaviour and `fix` when it repairs some — pick by
   what the change is, not how large it is. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Machine-Readable Result (required)

After implementing the story and running verification, return this exact JSON object as the LAST thing in your final response. The workflow captures it under the `impl_result` key — without it the node fails to parse and is retried:

```json
{
  "status": "done|blocked",
  "notes": "<what you implemented and verified, or what blocked you>",
  "exit_conditions": {
    "criteria": ["<acceptance criterion this turn satisfies>"],
    "commands": ["<command you expect to be green>"],
    "files": ["<file you expect to have touched>"]
  },
  "tests_added": ["<test file you wrote or extended>"],
  "no_test_reason": "<why there is no test, when there is none>"
}
```

- `status`: `"done"` only when the implementation is complete, verification passed, **and the code was run in a local environment with the touched story path exercised (Step 5)**. Use `"blocked"` if you could not complete it or could not run it locally.
- `notes`: a brief summary of what was implemented and verified, **including how you ran it locally and what you observed** (or the blocker).
- `exit_conditions`: the promise from Step 2, revised to what you actually mean by the end. Each `commands` entry is run to completion and each `files` entry is looked for in the diff — so state what is true, not what sounds thorough. Omit the whole object, or any list in it, when you have nothing to promise.
- `tests_added`: the test files this turn wrote or extended, service-relative. Only paths really in the diff count; naming a file you did not write comes back as a repair turn.
- `no_test_reason`: why there is none, when there is none. An exemption is weighed against what the service declares — it does not switch the check off.
{% if plan_text %}

---

## The Plan (inlined — authoritative)

The approved plan for this iteration, verbatim. This is the plan every step above refers
to — do not re-read it from disk.

{{ plan_text }}
{% if root_plan_text %}

### Cross-service contracts

The root plan carrying the implementation order and the contracts between services,
verbatim. Your work is still only the plan above; this is context, not extra scope.

{{ root_plan_text }}
{% endif %}
{% endif %}
{% if impl_instructions %}

---

## Coding Standards (inlined — authoritative)

The full text of every standard resolved in Step 1.2, verbatim from the repo. Do not
re-read these files; hold every rule below for each layer you touch.
{% for ins in impl_instructions %}

### `{{ ins.path }}`

{% if ins.text %}{{ ins.text }}{% else %}_(not inlined — read this file before writing code)_{% endif %}
{%- endfor %}
{% endif %}
