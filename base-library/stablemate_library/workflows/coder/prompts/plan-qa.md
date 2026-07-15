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

Do not rediscover or substitute another story. If validation routed back here, repair
the existing plan from the diagnostics instead of discarding valid scenarios.

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
2. `qa-plan.md`, the reviewable rationale and AC/obligation-to-scenario map.

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
    target: api
    mechanism: live
    covers:
      - ac:AC1
      - okf:required-obligation-id
    actions:
      - do: command
        id: exercise
        cmd: curl -s http://localhost:8080/health
        assert_contains: ok
        out: qa/steps/exercise.json
```

Only define targets the story needs. Every scenario has a target, mechanism, unique id,
`covers`, and at least one machine-executed assertion. `mechanism` is provenance
(`live`, `synthetic`, or `fixture`); `driver` is execution (`command`, `playwright`, or
`maestro`). Never use a driver name as a mechanism.

- `mechanism` is **required** on every step — missing mechanism is a hard validation error.
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
- expected observable result and evidence type; and
- why omitted optional journeys are outside impact.

<<<<<<< HEAD
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

**Forbidden as a verification basis:** A green test suite _alone_ never decides a pass. The plan's verification outputs (rendered template, grep results, CLI exit codes, observed UI behaviour) are the oracle. The test suite is necessary but not sufficient.
=======
Do not put verdicts in the plan and do not write anything under `qa/`. Do not invoke
`ostler qa validate` or `ostler qa run`; workflow script nodes do that after you return.
>>>>>>> 17f1b31 (Evolve skills)

## Output

<<<<<<< HEAD
## Choose the execution vehicle from the plan

The execution vehicle is determined by the **layer being tested**, not by the plan's Verification Commands. The plan's Verification Commands describe how the _implementer_ verified their own work — they are a useful context hint but are not the QA oracle. The QA oracle is user-observable behavior in the running app.

- **Mobile app:** Device interaction — tap, navigate, observe the screen. The QA skill for the mobile layer names the exact tooling.
- **Web app:** Live browser interaction against the deployed app. The QA skill for the web layer names the exact tooling.
- **Backend / API:** CLI calls against the running service — HTTP, RPC, event streams, or queue consumers. The QA skill for the backend layer names the exact tooling.
- **Infrastructure only (rendered config artifact):** Diff the rendered output (`helm template`, `terraform plan`). This is the narrow exception — applies only when there is no running app to exercise.
- **Multi-layer stories:** The runbook includes a section per layer, each with its own execution vehicle.

**Pick the oracle by where the behavior is observed, not by where the fix lives.** A backend-only
code change can still be reported, and specified, in terms of what a user sees on a screen (the
story/bug text says "in the app", "the caregiver sees", "shown on the dashboard", or an AC is
phrased as user-visible behavior rather than a data-layer claim). When that's the case, a
backend/API check alone — even a rigorous one (DynamoDB reads, EventBridge event capture) — does
**not** satisfy that AC by itself: it proves the data is correct, not that the user-visible symptom
the story reports is actually fixed. Plan the **UI oracle** (the mobile layer's UI-automation tool,
or the web layer's browser-automation tool — named by that layer's `qa_skill`) for any AC whose
claim is phrased at the UI, in addition to any backend check that supports it. Only substitute the
backend-only check when the story/AC text is itself phrased purely as a data/API-level claim with
no UI wording.

- If the UI oracle genuinely cannot run in this environment (e.g. a mobile layer's UI-automation
  tool requires a physical device or emulator), **check first, don't assume** — run the
  device/environment discovery check the layer's `qa_skill` specifies as a pre-flight step and
  look for a usable target before deciding the oracle is unavailable. If one is available, plan
  the UI flow as a normal, required runbook step (not `operator-only`) — a sandboxed agent
  environment does not, by itself, mean no device/target is present. Only mark that AC's UI
  confirmation `operator-only`/`Blocked` when the discovery step itself shows nothing available,
  and say so explicitly in the runbook with that check's output as proof.
- **If a story needs both a backend `qa-plan.yml` and a UI oracle, the UI oracle MUST be encoded
  as real `qa-plan.yml` steps too — never left as `qa-plan.md`-only prose.** `qa-story.md` treats
  `ostler qa run qa-plan.yml` as the execution vehicle once the file is present; a UI check
  described only in narrative form in `qa-plan.md` will not be executed and will silently vanish
  from the run, exactly like an unresolved CLI step would. Add the UI oracle's device/environment
  check, any recording daemon, and the flow invocation itself as ordinary `qa-plan.yml` steps,
  using the concrete tooling/recipe the layer's `qa_skill` and this repo's QA flavor document (see
  the `repo_qa_plan_yml_extra` extension point above).

If the plan's Verification Commands list source grep, unit tests, or static analysis — **ignore those as the QA vehicle**. Use the live-system tools for that layer instead. Source-level checks are background context; they are not QA steps.

For tool-specific guidance (how to write a particular type of QA script, conventions, setup), read the `qa_skill` instruction files listed in Required Context — they are the authority for each layer's tooling. This prompt does not duplicate that guidance.

## ACs that are impossible to verify locally

When `target_env=local` and an AC requires a **live cluster, production Grafana, deployed DNS, or cloud-only infrastructure**, that AC **cannot** be exercised locally. Mark it clearly:

- **Kind: `operator-only`** — the executor cannot verify this AC and should not attempt to; it requires a human with access to the live environment.
- Do NOT plan steps that pretend a local machine can reach a k8s cluster, Grafana, Loki, or DNS records it has no access to.
- Do NOT plan a shell script that calls `kubectl`, `curl` against cluster endpoints, or queries Grafana dashboards from localhost — these will fail and waste the QA loop.
- The QA executor should emit `blocked` for the whole story if **all** ACs are operator-only, or `passed` for the locally-testable subset and note the operator-only ACs in its report.

If every single AC requires live infrastructure and none can be verified locally, the runbook should say so at the top and instruct the executor to immediately emit `blocked` with a note explaining why.

## Beyond the criteria — walk the user journey and check coverage

Acceptance criteria are the floor, not the ceiling. A good manual QA exercises the **feature the way a user actually uses it**, end to end — that is what feature documentation is for. Plan two things on top of the per-AC steps:

- **Typical user-journey use cases.** If the repo documents this feature (a feature doc, a spec, a user-journey/flow description — name the file in the runbook), read it and plan steps that run the **representative end-to-end use cases** a real user performs on this surface, not just the literal AC assertions: the common happy path start-to-finish, plus the obvious adjacent actions a user would take in the same session (e.g. _open the editor → edit a field → add a collection item → save → navigate away and back → confirm it stuck_). The AC checks prove the change; the journey steps prove the feature still works as a whole around it. Where no feature doc exists, derive the journey from the story context + the source-of-truth surface and say so.
- **Proper automated coverage is in place.** For every behaviour you exercise by hand, plan a check that the implementation **also** carries automated coverage for it (unit/integration/e2e as the layer warrants) and that those tests actually pass — not just that the suite is green, but that _this_ behaviour is covered. Where a shipped behaviour or a journey step has **no** automated test, that is a gap the runbook must call out for the executor to record (a missing-coverage finding), so manual QA is not the only thing standing between a regression and production.

## Bringing the surface up (capable stack + run plan)

The runbook must tell the executor exactly how to stand each touched layer up and drive it. The workflow resolved a per-layer run plan from the plan's touched layers — fold it into the runbook's pre-flight:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}

- **{{ r.label }}**: follow {% for s in (r.qa_skills if r.qa_skills else [r.qa_skill]) %}`{{ s }}`{% if not loop.last %} + {% endif %}{% endfor %} — bring the layer up, drive the touched path with the tools its plan Verification Commands specify, and capture evidence. Include authenticated sign-in where the path requires it, and any code generation / contract compile checks the plan lists.
  {%- endfor %}
  {%- else %}
- _(No run plan resolved.)_ Fall back to the plan's `services` (each service's `type` + `path`) + **Verification Commands** / **Local run (smoke)** and the touched services' instruction files.
  {%- endif %}
  {% if qa_stack and (qa_stack.profile or qa_stack.fixtures) %}
  **Plan against the capable stack — with realistic data.** The story's **Verification setup** named the stack/profile and data this surface needs to render; the plan carried it forward as `qa_stack`{% if qa_stack.profile %} (stack: {{ qa_stack.profile }}){% endif %}. The runbook's pre-flight must bring up **that** stack with those fixtures present — not a thin/empty default. A surface seen blank for lack of data is a Fail to be caught, so the plan must seed the data first.
  {% endif %}

The pre-flight section of the runbook must list: the stack/profile to start, the fixtures/seed to load, the authenticated sign-in step, and a health check, so every per-AC step below it is immediately runnable.

## Independent oracle (contract-consuming surfaces)

If a touched layer consumes an external contract (an API payload, another producer's output), a green unit suite is **not** sufficient — the tests and code share an author and can encode the same wrong assumption. For such a layer, the runbook must include a step that verifies the surface **against a real instance of that contract** from an environment independent of the local dev stack and the code's own fixtures (the reference/legacy mirror for a rewrite repo; a deployed/staging env for greenfield), captures the real payload to `{{ workhorse_var('qa_dir') }}`, and compares the rendered behaviour against it. Keep any deployed-env step **read-mostly** against a dedicated **test tenant/account**. If the repo declares no independent oracle for this surface, say so in the runbook and the step is a no-op (it must not block).

{% block repo_qa_evidence_rules %}{% endblock %}

## qa-plan.md structure

```markdown
# QA Plan: <Story Name>

## Verification basis (read first)

- Verdicts come from the plan's verification outputs against the expected state.
- A green test suite alone NEVER decides a pass.
- Execution vehicle: <derived from the plan's Verification Commands per layer — name the script(s)>. Reusable on re-QA.

## Pre-flight — bring the surface up

- QA script (execution vehicle): <path to the script the executor will run — reused on re-QA>
- Stack/profile to start: <… or "N/A — no local application stack required">
- Fixtures / seed to load: <… or "None">
- Sign-in (real flow, test user): <… or "N/A — no application sign-in needed">
- Device/target check (UI-automated layers only): run the discovery check the layer's `qa_skill`
  specifies and record the output. A usable device/target means the UI-oracle AC(s) below are
  `local` (run them); nothing available means they are `operator-only` for this run — do not
  guess, check.
- Lessons applied (from `docs/qa/lessons.md`): <known traps this run pre-empts, or "none on file">
- Health check: <…>
- Source-of-truth reference: <path to evidence, or the oracle to capture from, or "rendered output from CLI tools">
- Repo roots (multi-repo): <env vars the script needs, e.g. `API_SERVICE_ROOT`, `WEB_APP_ROOT`>

## AC1 — <criterion text>

- Kind: <`local` (exercisable locally) or `operator-only` (requires live infra — executor should skip)>
- Action (as a user/operator): <…>
- Expected observation: <…>
- Source-of-truth comparison: <…>
- Evidence to capture: <`{{ workhorse_var('qa_dir') }}/<file>` — text or image depending on the vehicle>
- Pass rule: <one line — what must be true to pass>

## AC2 — <criterion text>

- …

## Typical operator-journey use cases

<representative end-to-end use cases, or "N/A — infrastructure change only">

## Required success gates (must all pass)

- Every locally-testable AC exercised (action performed, observed, compared)
- Proper automated coverage exists for the behaviour exercised (missing coverage recorded)
- Tests + lint/format + build pass (necessary, NOT sufficient)

## Evidence manifest

- `{{ workhorse_var('qa_dir') }}/<file>` — what it proves (one line per AC)
```

Rules for the runbook:

- No verdicts in this file — it is the plan; the executor fills verdicts. State the **pass rule** instead.
- One AC section per acceptance criterion, in story order. Never collapse two criteria into one step.
- Every step copy-paste runnable; no bare `<placeholder>` without a preceding discovery command.
- Evidence paths are **absolute** paths under `{{ workhorse_var('qa_dir') }}`, never bare/cwd-relative names.
- Keep language operational — action, expected observation, pass rule.
- Only reference tools the plan's Verification Commands actually use — do not introduce tools the plan does not call for.

## Structured Output Requirement

Return this exact JSON object in your **final response** (after the short confirmation). The workflow REQUIRES this exact structure:
=======
Return JSON only:
>>>>>>> 17f1b31 (Evolve skills)

```json
{
  "qa_plan_result": {
    "status": "done",
    "notes": "Wrote qa-plan.yml and qa-plan.md with complete AC and OKF coverage."
  }
}
```
