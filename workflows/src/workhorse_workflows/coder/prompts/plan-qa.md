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
{% if workhorse_var('context_notes') %}- Context diagnostics: `{{ workhorse_var('context_notes') }}`
{% endif %}{% if workhorse_var('plan_validation_notes') %}- Previous plan validation diagnostics: `{{ workhorse_var('plan_validation_notes') }}`
{% endif %}{% if workhorse_var('plan_review_notes') %}- Previous semantic plan-review diagnostics: `{{ workhorse_var('plan_review_notes') }}`
{% endif %}{% if workhorse_var('run_assessment_notes') %}- Previous execution-assessment diagnostics: `{{ workhorse_var('run_assessment_notes') }}`
{% endif %}{% if workhorse_var('audit_notes') %}- Previous independent-audit diagnostics: `{{ workhorse_var('audit_notes') }}`
{% endif %}{% if workhorse_var('evidence_notes') %}- Previous deterministic evidence diagnostics: `{{ workhorse_var('evidence_notes') }}`
{% endif %}
A diagnostics line appears only when that gate actually reported something to fix, so **no
diagnostics lines at all means no gate has complained** — author the plan fresh rather than
hunting for the finding that is missing from this brief.

Do not rediscover or substitute another story. If a gate did route back here, repair the existing
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
        id: observable-behavior-exercise
        cmd: curl -s http://localhost:8080/health
        assert_contains: ok
        out: qa/steps/observable-behavior-exercise.json
```

Only define targets the story needs. Every scenario has a target, mechanism, unique id,
explicit objective, asserted causal preconditions, observable checkpoints, `covers`, and at
least one machine-executed terminal assertion. `mechanism` is provenance
(`live`, `synthetic`, or `fixture`); `driver` is execution (`command`, `playwright`, or
`maestro`). Never use a driver name as a mechanism.

- `mechanism` is **required** on every scenario — missing mechanism is a hard validation error.
- An action `id` must be unique across the **whole plan**, not just within its scenario. The
  example's `observable-behavior-exercise` is prefixed with its scenario id for exactly this
  reason: writing six scenarios by copying the example verbatim yields six actions called
  `exercise`, and every one after the first is a validation error. Namespace every action id to
  its scenario — the scenario id, or a short unambiguous abbreviation of it (`create-group-success`
  → `cgs-create`, `cgs-assert-shape`).
- An action declares **exactly one** of `do`, `expect`, or `capture` — that key names what the
  action *is*, so a second one is a hard validation error rather than a richer step. Asserting on
  a `do: command` is not a separate key: it is the `assert_contains` / `assert_count` /
  `expect_http` / `cloudwatch_confirm` field on the command action itself, as the example shows.
  `expect:` takes a UI predicate (`visible`, `hidden`, `enabled`, `disabled`, `selected`,
  `checked`, …) and belongs to the playwright/maestro drivers; `capture:` takes an artifact kind
  (`screenshot`, `trace`, `body_text`, `accessibility_snapshot`, `view_hierarchy`). Splitting a
  step into exercise-then-assert means **two actions**, each with its own id.
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
- Use `{% raw %}{{key}}{% endraw %}` to reference values captured by prior steps (not shell variables).
- Use `{% raw %}{{env.NAME}}{% endraw %}` for env-block values.
- Payload files referenced in a step command must be written to `qa/payloads/` **before** the plan runs — include a `fixture` step or note them as pre-existing files.
- `assert_count: 1` is the no-duplicate check — use it on queries where exactly one result is expected.
- Background daemons must be declared in `background:` — the executor starts/stops them; the agent must NOT start them manually. `background:` is for **foreground in-QA services** scoped to the run (a dev server pinned to branch source, an event tail). The **heavyweight stack** (docker compose, emulators, the DB + baseline seed) is NOT declared here — it is owned by the workflow's `ensure_stack` step via the repo's `qa-stack.yml` manifest, brought up before the plan runs and left up for reuse. Assume it is already serving; do not bring it up in the plan.
- Each `background:` daemon takes an optional `ready_check` — what the executor polls before scenario 1, plus a `timeout:` in seconds (default 30). Two forms, and picking the wrong one blocks the whole run: a **string** is fetched and must answer HTTP 200, so use it only when the service really has a `GET` that does; otherwise use a **mapping** `{cmd, assert_contains}`, which is ready when the command exits 0 and its stdout contains the needle. A service whose only route is a `POST` has no 200-answering URL, so it needs the mapping. The command runs in the daemon's own working directory.
{% raw %}  ```yaml
  background:
    - name: api-server
      cmd: cd api && go run ./cmd/server
      timeout: 60
      ready_check:
        cmd: >
          curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8080/links
          -H 'Content-Type: application/json' -d '{"longUrl":"https://example.com/probe"}'
        assert_contains: "201"
  ```{% endraw %}
- The `qa_dir` path for evidence files is `{{ workhorse_var('qa_dir') }}` — use `qa/steps/` and
  `qa/asserts/` as sub-directories. **`out:` and `capture:` paths are the only ones resolved for
  you**; ostler resolves them against the spec directory and creates their parents. A step's `cmd`
  runs with its working directory at the **repo root**, so the identical string means a different
  place inside a command: `out: qa/steps/x.txt` lands in `{{ workhorse_var('qa_dir') }}/steps/`,
  while `curl -o qa/steps/x.txt` inside a `cmd` targets `<repo>/qa/steps/`, which does not exist —
  the redirect fails, the command dies with empty stdout, and every assertion downstream of it
  fails against an implementation that is correct. Chain state between actions with `capture:` +
  `{% raw %}{{key}}{% endraw %}`, not with hand-written temp files. If a command genuinely must
  write a file itself, give it the **absolute** `{{ workhorse_var('qa_dir') }}/steps/…` path.
- **Never put time/entropy expressions (`$(date +%s)`, `$RANDOM`, `$(uuidgen)`) directly in a `live` or `synthetic` step's `cmd`.** These re-evaluate on every execution. A login step and a logout step with different `$(date +%s)` values create two independent sessions — the logout never closes the session the login opened, and the subsequent lookup finds nothing. Generate the value once in a `fixture` step, capture it, then reference `{% raw %}{{key}}{% endraw %}` in all steps that need it:
{% raw %}  ```yaml
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
  ```{% endraw %}
  `ostler qa validate` enforces this and will reject a plan that puts `$(date` in a non-fixture step.
**Every Playwright locator and every URL comes from the book, not from the running page and
not from your memory of it.** `ostler qa validate` enforces this statically and will reject
the plan — it is a gate, not a preference. The packet carries what you need on the
obligation itself:

- A `locators` object on an obligation holds that node's own `selector`, `role`, `name`,
  `keyboard`, `route`, `entry` and `params` bullets. Address the element by `role` + `name`
  (`get_by_role("alert", name=…)`); use `selector` only when the node states one; fall back
  to a text locator only when the node documents neither, and say so in the scenario.
- A node's documented `role` is the *intended* semantic, not a guarantee of what the target
  engine's accessibility tree actually computes for that markup. Native disclosure elements
  (`<summary>` inside `<details>`) are the known case: several engines expose the summary as
  `group`, not `button`, so a `role: button` locator against it times out with zero matches
  even though the element renders correctly. When the node's underlying element is a native
  `<summary>`/`<details>` pair, use its `selector` (or a CSS locator scoped to a stable class
  or `:has-text(...)`) instead of `role`+`name`, and say so in the scenario — don't spend a
  repair cycle rediscovering this at review time.
- Playwright's `expect: visible` is strict-mode: it throws (not "false") when a locator
  resolves to more than one element, even if every match is legitimately present and
  visible. Before asserting `visible` on a locator, check whether the book or the fixture
  implies more than one match is possible; if so, scope the locator narrower (a parent
  container, `:first-child`/`:nth-child`) or assert `count` at the expected number instead
  of a bare `visible`.
- A text locator invented by reading the implementation — or guessed from a rendered string —
  is a defect, not a shortcut. It is the thing that breaks on the next copy edit, and it is
  why a plan that "passed" proves nothing about the accessible name the book requires.
- Navigate to the `route` the screen documents, entering by its `entry` path and supplying
  its `params`. Never compose a URL the book does not state.

Use runner-supported common actions for Maestro. Advanced cases may point to committed
native Playwright tests or Maestro flows, but Ostler still owns invocation, timeout,
cleanup, artifacts, recordings, and verdicts. Declare services/background processes in the
plan; do not start them here.

Each AC and required OKF obligation must resolve in `covers` and have an executable
assertion. A source check, unit test, build, or narrative is not behavioral evidence.
An obligation marked `"required": false` (rendered `_(context only — not owed evidence)_`)
names something this story neither built nor touched — an endpoint with no implementation
behind it, a screen no change reached. Read it for context; do not write a scenario against
it, and do not invent a route to reach it.
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
are the oracle. Do not put verdicts in the plan or write under `qa/`.

Do not validate the plan yourself, by any route: not `ostler qa validate`, not `ostler qa run`,
and not by importing `ostler.qa` from Python. A workflow script node validates it the moment you
return and hands you its diagnostics if it fails, so a self-check can only repeat a verdict that
is one call away. The Python route is named explicitly because forbidding the two commands alone
left it open, and a run took it: four Bash turns rediscovering `load_plan`'s signature, inside a
turn that spent ten minutes and a quarter of the run's whole wall-clock budget arriving where the
node arrived immediately afterwards.

## Output

Return JSON only:

```json
{
  "status": "done",
  "notes": "Wrote qa-plan.yml and qa-plan.md with complete AC and OKF coverage."
}
```
