---
agent: agent
---

Implement this plan. Follow these steps in order.

## Provided Inputs (authoritative — do not rediscover)

The workflow supplies these values. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec/artifact directory: `{{ workhorse_var('spec_dir') }}`
- Service path: `{{ workhorse_var('service_path') }}`
- Service type: `{{ workhorse_var('service_type') }}`
- Verification command: `{{ workhorse_var('verification') }}`
- Gates that run after this turn: {{ workhorse_var('gates') or '(nothing declared)' }}

The gate line above is what the workflow will actually run once you report `done`, taken
from this service's declaration — not a guess, and not a list to add to. Run those commands
yourself before finishing and leave them green; a red one comes straight back to you as a
repair turn with its output attached. Where it says nothing is declared, no gate will run
and there is no command for you to invent.

Your CWD is the repo containing the service above. All code changes go in this repo. The service root is `{{ workhorse_var('service_path') }}` within this repo — focus changes there and its dependencies (shared packages in the same repo).

Implement **only** the plan you were handed for this iteration. Do NOT search other repos, git history, or branch state to guess which story to implement, and do NOT substitute a different service.

If the story path is blank or its file does not exist, return `status: "blocked"` (Machine-Readable Result below) with notes saying the workflow did not provide a usable story path — that hands it to the operator. Do not pick a story yourself.

{% if operator_context %}
## Operator answer (authoritative ground truth)

You raised a block on this story and an operator answered it. Treat the following as fact: it
overrides any earlier assumption in the story, the plan or the code. Do **not** re-derive it,
second-guess it, or raise the same block again — it has been answered.

{{ workhorse_var('operator_context') }}
{% endif %}

## Step 1 — Read and Prepare

Before writing any code:

1. Read the story — your plan is inlined under **"The Plan"** at the end of this prompt; it is already in front of you, so do not spend a turn reading it from disk. **The story's Acceptance Criteria are the bar — your job is to make ALL of them true**, as a person using the running app would observe them, at parity with the named source of truth. **Cover the whole goal**: if satisfying a criterion requires fixing a root cause that spans the surface (e.g. state keyed wrong across every field, labels untranslated everywhere, a missing nav/section), that whole fix is in scope — do not implement a narrow symptom-patch that leaves the criterion only partly met. This may take **several passes**: QA will exercise each criterion against the source of truth and fail anything not actually met, looping you back here. The story's `## Context` links the documentation it is grounded in; read those links for grounding, but the Acceptance Criteria — not the docs — define done.
   - A *different* surface or an unrelated defect you pass through is not this story's: leave it alone, and say so in the result notes. Never absorb it, and never treat it as an excuse to leave this story's own criteria unmet.
2. Load this repo's installed coding standards for the files you are about to edit — the
   skill index advertises what applies where, and a service can mix languages, so the
   standard that binds is a property of the file, chosen as you reach it. Docs-only work
   also covers the repo's `AGENTS.md`, and a layer's testing skill before you write or
   update its tests.
3. The plan's **Verification Commands** section carries the canonical test, codegen, lint, and build commands, and **Provided Inputs** carries this service's gates. Those are the commands you run — do not hunt through instruction files for others, and do not invent any.
4. Where the plan leaves a detail open, make the reasonable design decision yourself and record it in the implementation notes — the planning gates are behind you, and a block here costs an operator round-trip. Reserve `blocked` for what a decision cannot get past (an operator-only foundation, per Step 5).

---

## Step 2 — Build a Task List

Turn the plan's stages and tasks into a todo list, using the task/todo tool available in the
current assistant environment. Complete every entry — the plan is the scope, and a stage you
leave undone is work the story is missing.

---

## Step 3 — Implement in Batches, Then Verify

Spend your turns on edits, not ceremony: **batch independent file writes and edits into the
same response wherever your tools allow.** A turn that writes one small file and stops is
latency spent on nothing — when the plan names five files whose contents you already know,
write all five in one turn. Serialize only where a later edit genuinely depends on an
earlier command's output (generated code, a failing test's message).

### 3a. Write the code and its tests, together

- Work the task list in order; implement each task fully — production code **and its tests
  in the same pass**. **Every new behavior must have a corresponding test.** Not optional.
  Where the behaviour is observable, leading with the failing test is the cheaper order:
  you find out what the code has to do before you write it.
- Follow the plan's file paths, function names, and patterns exactly, and enforce the
  target layer's instruction rules for every edit.
- Map each test to the plan's **Given / When / Should** cases; add assertions for new
  functions, branches, error conditions, and state transitions.
- **For a component that consumes an external contract** (an API payload, another producer's output), derive its test fixtures from a **captured real payload** (a golden file recorded from the real producer), not a hand-authored shape. A fixture you invent can encode the *same wrong assumption* as the code it tests — then both agree and the suite passes green over a real bug. Record the real payload and assert against it.
- Before editing a layer's tests, load that layer's **testing skill** from the ones this
  repo installs and treat it as canonical for test naming, fixtures, integration-test shape
  and assertion conventions — if this prompt appears to disagree with it, follow the skill.

### 3b. Run code generation when its inputs change

- When your edits modify files that feed into code generation (an OpenAPI/GraphQL spec, a generated API client, mocks, etc., per the plan's **Code Generation & Build Artifacts** section), run the generation command from the plan's **Verification Commands** before writing code that depends on the generated output, and verify it compiles.

### 3c. Verify once, as a batch

- When the implementation tasks are done, run the verification **once, as a batch**: the
  gate commands from **Provided Inputs** plus the test command from the plan's
  **Verification Commands** section. Do **not** re-run the full gate set after every
  task — the per-task loop is where runs go to spend their wall clock.
- **If a check fails, fix the code immediately and re-run what failed**, then the batch
  once more; watch for regressions in related tests.
- Use the available diagnostics/analyzer output to confirm no compile/type errors remain
  before calling the work done.

### 3d. Mark complete

- Confirm the finished tasks match the plan, then mark them `completed` — marking several
  at once right after a green verify is fine; claiming one before its check ran is not.

---

## Step 4 — Final Verification (BLOCKING)

After all implementation tasks are done, run every command from the plan's **Verification Commands** section in order:

1. **Code generation**: Run all codegen commands. Verify output files are up to date. (Skip if plan says "None".)
2. **Tests**: Run the full test command. All must pass.
3. **Lint / Format**: Run the lint/format command. Fix any issues.
4. **Build**: Run the build command. Confirm it succeeds.
5. **Plan review**: Confirm every file in the plan was modified and every success criterion is met.
6. **Standards**: Verify all edits conform to the standards you loaded for the files you changed.

**Per-service verification**: Run the verification command for this service: `{{ workhorse_var('verification') }}`. This is the canonical build/test/lint command from the repo's agents.yml.

**Generated client code is first-class**: when the plan regenerates an API client in any language, treat the generated package as app code — do **not** hide analyzer/type failures by excluding it. If generated-API analysis fails, fix the generation inputs, the generated package's dependencies, or the regeneration flow until both the app and the generated package pass.

**Story success gate**: Before considering implementation complete, every touched layer must be cleanly formatted, linted/analyzed, tested, and built — using the exact commands from the plan's **Verification Commands** section. Agent toolkit config or source changes additionally require `farrier --check` to leave generated adapter files current.

**Do not consider the work complete until all required checks pass for every touched layer.**

---

## Step 5 — Smoke It (BLOCKING)

Green tests are not proof the code boots. Before you may return `status: "done"`, bring up
each layer this story touched and hit the path you changed **once**:

- Use the plan's **"Local run (smoke)"** command for the layer, or the layer's QA skill
  named below where the plan has none. Do not invent commands, and bound every
  long-running process with a wall-clock `timeout`.
- Run **only** the layers the plan touches — a frontend-only story does not start the API,
  and a docs-only story (`services` all `type: docs`, or empty) has no runtime at all: skip
  this step and say so in the result notes.
- **A boot failure is yours to fix now** — a panic, connection-refused, a boot-time 500, a
  blank page, a route that bounces. Anything deeper than "it comes up and answers once"
  belongs to QA, which walks every acceptance criterion after you.
{% if qa_run_plan %}
The workflow decoded the plan's touched layers; each entry names the layer's QA skill, which
holds its local-run command and its success signal:
{%- for r in qa_run_plan %}
- **{{ r.label }}** — bring it up per `{{ r.qa_skill }}` and exercise the touched path.
{%- endfor %}
{%- endif %}
{% if verification_setup and verification_setup.profile %}
Bring up **{{ verification_setup.profile }}** rather than whatever thin default is already
running — the story named it as the stack this surface needs.
{% endif %}
Never leave a stack backgrounded in your shell for QA to inherit: a process the workflow
does not own dies at node teardown.

If a touched layer's local environment **genuinely cannot be brought up** here, do **not**
report `done` — return `status: "blocked"` naming exactly what was missing. "Unit tests
passed but I could not run it" is **`blocked`, never `done`.** `blocked` is reserved for an
**operator-only foundation** (no Docker, a real credential, a real deploy). A missing
fixture, seed, migration, stored procedure, or data row the surface needs is *not* blocked —
building it is in scope for this story.

{% block repo_impl_rules %}{% endblock %}

---

## Rules

**Never do this:**

- Mark a task complete before the check that covers it has passed.
- Continue with compile errors or failing tests.
- Skip code generation when the plan identifies generated files.
- Invent a verification command; use the plan's and **Provided Inputs**'.
- **Hand-edit the story's `status:` frontmatter or its `## Implementation Status` **Status** line.** See "Story Status" below.
- Apply the wrong layer's instruction set.

**Always do this:**

- **Run every gate command from Provided Inputs in the service directory before declaring
  `done`**, and fix every finding — formatting, unused imports, and any accessibility
  findings for UI work (missing labels/roles, unnamed controls). Follow the loaded
  accessibility skill for UI surfaces. The workflow re-runs these and routes a failure
  straight back to you, so leaving one dirty does not finish the story faster.
- **Smoke the touched layers (Step 5) before declaring `done`.**
- Batch independent file writes into one turn; serialize only on genuine dependencies.
- Run code generation before testing when generated files are involved.
- Fix errors immediately — never defer them.
- Re-read the plan section before coding each step.

## Story Status

Leave the story's `status:` frontmatter and its `## Implementation Status` **Status** line
exactly as you found them — record what you ran as prose under that heading instead. A gate
re-reads that line after this turn and sends the story back to you if it changed.

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Machine-Readable Result (required)

After implementing the story and running verification, return this exact JSON object as the LAST thing in your final response. The workflow captures it under the `impl_result` key — without it the node fails to parse and is retried:

```json
{
  "status": "done|blocked",
  "notes": "<what you implemented and verified, or what blocked you>"
}
```

- `status`: `"done"` only when the implementation is complete, verification passed, **and the touched layers were smoked (Step 5)**. Use `"blocked"` if you could not complete it or could not run it locally.
- `notes`: a brief summary of what was implemented and verified, **including how you ran it locally and what you observed** (or the blocker).

---

## The Plan (inlined — authoritative)

The approved plan for this iteration, verbatim. This is the plan every step above refers
to — do not re-read it from disk.

{{ plan_text }}
