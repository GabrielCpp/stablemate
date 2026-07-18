---
agent: agent
---

# Plan QA For A {{ repo.name | title }} Story

Author the complete, machine-executable QA plan for one reviewed story. Do not execute
QA. Ostler is the only primary executor for command, browser, and mobile scenarios.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Context status: `{{ workhorse_var('context_status') }}`
- Context diagnostics: `{{ workhorse_var('context_notes') }}`
- Previous plan validation diagnostics: `{{ workhorse_var('plan_validation_notes') }}`
- Previous semantic plan-review diagnostics: `{{ workhorse_var('plan_review_notes') }}`
- Previous execution-assessment diagnostics: `{{ workhorse_var('run_assessment_notes') }}`
- Previous independent-audit diagnostics: `{{ workhorse_var('audit_notes') }}`
- Previous deterministic evidence diagnostics: `{{ workhorse_var('evidence_notes') }}`

Do not rediscover or substitute another story. If any gate routed back here, repair the existing
plan from its specific diagnostics instead of discarding valid scenarios. Newer semantic,
assessment, audit, or evidence findings are not superseded by an earlier structurally valid result.

## Required Inputs

Read all of:

- the story and its acceptance criteria;
- `<spec_dir>/qa-okf-context.json` as the machine-readable impact authority;
- `<spec_dir>/qa-okf-context.md` as its human rendering;
- `plan-context.json`, implementation plans, review results, and applicable QA skills;
- `docs/qa/lessons.md`, when present; and
- static inputs under `<spec_dir>/qa-inputs/`, when present.

The verification contract is the union of story acceptance criteria and every required
OKF obligation. Include impacted contract and journey completion conditions, consistency
groups, persistence, producer-to-consumer events, concurrency, and idempotency. Never
drop an obligation because it is inconvenient or because a nearby assertion looks
similar.

## Required Outputs

Write both files directly under the spec directory:

1. `qa-plan.yml`, mandatory for every surface and every run.
2. `qa-plan.md`, the reviewable rationale and AC/obligation-to-scenario map. Create it through
   `ostler` first — `timeout 30 ostler create spec <story-name> qa-plan.md`, where `<story-name>`
   is the folder name of the spec directory — which stamps its `type: spec.qa-plan` frontmatter.
   Write the structure below **underneath that `---` block, leaving it in place** — a doc with no
   `type:` is an `okf-missing-type` error against the graph.

There is no UI/mobile escape from YAML. Playwright and Maestro are drivers selected by
the YAML plan, not agent-operated alternatives. Command/API verification uses the same
plan. Inputs required before execution belong in `qa-inputs/`; nothing required to start
a run may live under disposable `qa/`.

## YAML Contract

Use the current universal plan schema:

```yaml
version: 2
run_id: <stable story run id>
story: <story slug>

inputs: {}

targets:
  api:
    driver: command
  web:
    driver: playwright
    base_url: http://localhost:3000
    browser: chromium
    recording:
      required: true
      mode: window
  mobile:
    driver: maestro
    app_id: com.example.app
    device: android
    recording:
      required: true
      mode: device

scenarios:
  - id: observable-behavior
    objective: Call the health endpoint and observe the ready response
    preconditions:
      - the service health check reports ready
    checkpoints:
      - the request reaches the running service
      - the response is successful and contains the expected state
    forbid:
      - unexpected 5xx responses
    target: api
    mechanism: live
    covers:
      - ac:1
      - okf:required-obligation-id
    actions:
      - do: command
        id: exercise
        cmd: curl -s http://localhost:8080/health
        assert_contains: ok
        out: qa/steps/exercise.json
```

Only define targets the story needs. Every scenario has a target, mechanism, unique id,
explicit objective, asserted causal preconditions, observable checkpoints, `covers`, and at
least one machine-executed terminal assertion. `mechanism` is provenance
(`live`, `synthetic`, or `fixture`); `driver` is execution (`command`, `playwright`, or
`maestro`). Never use a driver name as a mechanism.

- `mechanism` is **required** on every scenario — missing mechanism is a hard validation error.
- **Never write a stub/placeholder `cmd`** (e.g. `echo 'REPLACE THIS COMMAND: ...'`) for a step you
  can't fully resolve at planning time. If no `plan-context.json` or pre-resolved fixture exists,
  write the **real** discovery command using the tooling the layer's `qa_skill` names so the step
  is executable by `ostler qa run` unattended. A `cmd` that is prose describing what someone else
  should type is not something `ostler qa validate` can catch, and it forces the executor into
  exactly the manual-fallback bypass this file format exists to prevent — every step must be
  something ostler itself can run.
- **Do not invent CLI flags, REST routes, or output shapes.** Every `cmd` must use flags/endpoints
  that actually exist (check the tool's `--help`, source, or the layer's `qa_skill` — do not guess
  by analogy with a similar-looking tool), and `capture:`/`assert_count` must match the command's
  **real** output shape (e.g. don't JSONPath-capture from a command that prints plain text).
- Use `{{key}}` to reference values captured by prior steps (not shell variables).
- Use `{{env.NAME}}` for env-block values.
- Payload files referenced in a step command must be written to `qa/payloads/` **before** the plan runs — include a `fixture` step or note them as pre-existing files.
- `assert_count: 1` is the no-duplicate check — use it on queries where exactly one result is expected.
- Background daemons must be declared in `background:` — the executor starts/stops them; the agent must NOT start them manually.
- The `qa_dir` path for evidence files is `{{ workhorse_var('qa_dir') }}` — use `qa/steps/` and `qa/asserts/` as sub-directories.
- **Never put time/entropy expressions (`$(date +%s)`, `$RANDOM`, `$(uuidgen)`) directly in a `live` or `synthetic` step's `cmd`.** These re-evaluate on every execution. A login step and a logout step with different `$(date +%s)` values create two independent sessions — the logout never closes the session the login opened, and the subsequent DynamoDB lookup finds nothing. Generate the value once in a `fixture` step, capture it, then reference `{{key}}` in all steps that need it:
  ```yaml
  - id: gen-device-id
    mechanism: fixture
    cmd: printf '{"device_id":"qa-prefix-%s"}' "$(date +%s)"
    capture:
      device_id: $.device_id
  - id: login
    mechanism: live
    cmd: curl -H "Device: {{device_id}}" ...
  - id: logout
    mechanism: live
    cmd: curl -H "Device: {{device_id}}" ...   # same ID — closes the right session
  ```
  `ostler qa validate` enforces this and will reject a plan that puts `$(date` in a non-fixture step.
Use role/label locators before CSS for Playwright. Use runner-supported common actions
for Maestro. Advanced cases may point to committed native Playwright tests or Maestro
flows, but Ostler still owns invocation, timeout, cleanup, artifacts, recordings, and
verdicts. Declare services/background processes in the plan; do not start them here.

Each AC and required OKF obligation must resolve in `covers` and have an executable
assertion. A source check, unit test, build, or narrative is not behavioral evidence.
Stateful behavior must exercise action, persistence, reload/re-query, and isolation.
Contract consumers must use a real producer when the repository declares one.

## Markdown Contract

`qa-plan.md` must explain:

- preflight, targets, fixtures, credentials by symbolic reference, and health checks;
- one section per acceptance criterion in story order;
- one section listing every OKF obligation from the context packet;
- scenario and assertion coverage for each AC/obligation;
- each scenario's objective, causal preconditions, intermediate checkpoints, forbidden bypasses,
  and terminal proof;
- expected observable result and evidence type; and
- why omitted optional journeys are outside impact.

**State and verify the bug's causal precondition explicitly — never just assume it from fixture
construction.** Most bugs reproduce only under a specific shared condition named or implied by the
story (the same location/room, the same session, the same tenant, the same parent record). When a
fixture-discovery step picks the entities the AC will exercise, that precondition is often true
only because of _how the query happened to be built_ (e.g. scoped to one partition key) — which is
easy to get subtly wrong without anyone noticing. Don't let it stay implicit: capture the shared
value itself (not just the entity IDs) in the discovery step's own evidence output, and state in
the AC's action/pass-rule that this precondition was confirmed, not assumed. A runbook that never
surfaces this check can pass while accidentally testing two entities that don't actually share the
condition the bug depends on — which proves nothing about the bug.

Use the OKF graph as a cross-layer test specification, not as a list of titles:

- Start every impacted `flow` at its documented `start`; do not deep-link past navigation or
  setup that can expose integration failures. Assert its documented `end` and fail on any
  unexpected 5xx, crash, or browser console error during the journey.
- Exercise every emitted obligation for `when`, `does`, `states`, `keyboard`, status/error/auth,
  return/raise, and field semantics. Include happy, negative, retry, reload, role, locale, and
  accessibility cases when those requirements appear in the packet.
- Traverse linked contracts across the actual producer and consumer. A controller mock does not
  prove a pooled-session, persistence, wire-format, or rendered-consumer obligation.
- Treat `verificationRefs` as leads, not proof. Determine whether each reference is unit,
  integration, mocked UI, or real-stack journey and whether its suite runs by default. An excluded
  or manually invoked test cannot stand in for live evidence or a default regression gate.
- For each scenario with `covers`, capture at least one runner-owned artifact that demonstrates
  the asserted result. A passing exit code with no criterion-specific artifact is insufficient.

A green test suite alone never decides a pass. The observable behavior and runner-owned evidence
are the oracle. Do not put verdicts in the plan, write under `qa/`, or invoke `ostler qa validate`
or `ostler qa run`; workflow script nodes do that after you return.

## Output

Return JSON only:

```json
{
  "qa_plan_result": {
    "status": "done",
    "notes": "Wrote qa-plan.yml and qa-plan.md with complete AC and OKF coverage."
  }
}
```
