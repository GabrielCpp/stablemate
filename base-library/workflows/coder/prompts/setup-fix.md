---
agent: agent
---

# Make the Dev Environment QA-Capable — {{ repo.name | title }}

The QA stack could not be brought up — QA was **blocked**, or the workflow's durable bring-up step
(`ensure_stack`) could not stand the stack up. This is a *setup* problem, not a product one. Your job
is to make the stack **bring-up-able by the workflow** — so the next `ensure_stack` pass stands it up
and QA can drive the running app.

**You do not start services and leave them running.** A long-running stack the workflow does not own
dies at node teardown — that exact pattern is what burned three QA attempts on a real run. The
workflow owns stack lifecycle through a declarative **stack manifest** (`qa-stack.yml`); your job is to
make that manifest and the things it needs correct, then hand back. Concretely, the fixable problems
are: a missing or wrong `qa-stack.yml`, a bring-up/seed/health command in it that fails, missing
tooling or dependencies it calls, or a broken local config file one of its steps needs. Only a blocker
that genuinely needs a human (a real secret/credential that cannot be generated locally, a
deployed/preview environment, or hardware) is `unfixable` → report that and the workflow escalates to
the operator.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`

## What QA was blocked on

The blocking QA notes (read them — they name what could not run):

```
{{ workhorse_var('qa_notes') }}
```

## Required Context

Read, then act:

- `qa-stack.yml` at the repo root (if present) — the **stack manifest** the workflow's `ensure_stack`
  step runs. It declares `entry_url`/`health_path`, `launch` (the bring-up or foreground command),
  ordered `prepare`/`seed`/`health` steps, and an optional `stop`. This is the artifact you repair; if
  it is absent and the stack needs standing up, **author it** from the repo's documented commands.
- `{{ workhorse_var('spec_dir') }}/qa-plan.md` — the QA runbook. Its **pre-flight** names the stack,
  services, tools, fixtures and sign-in the ACs need. That pre-flight is your checklist of what the
  manifest must bring up.
- `AGENTS.md` and the project's **developer / local-stack runbook** — the documented way to stand up
  this repo's environment (the `make` targets, compose profiles, emulator/devstack start commands,
  seed/fixture commands, tool installs). These are what the manifest's steps should call. **Prefer
  these documented commands over improvising.**
- the touched layers' QA skills (resolved for this story) — each says how to bring its layer up and
  which tool drives it (curl / Playwright / Maestro / `pulumi preview`):
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
  - **{{ r.label }}**: {% for s in (r.qa_skills if r.qa_skills else [r.qa_skill]) %}`{{ s }}`{% if not loop.last %}, {% endif %}{% endfor %}
{%- endfor %}
{%- else %}
  - _(none resolved — fall back to the plan's Verification Commands / Local run (smoke))_
{%- endif %}
{% if qa_stack and (qa_stack.profile or qa_stack.fixtures) %}
- The **capable stack** the surface needs: {% if qa_stack.profile %}profile `{{ qa_stack.profile }}`{% endif %}
  with its fixtures present. Bring **that** stack up — not a thin/empty default.
{% endif %}

## What you may do (make the stack bring-up-able)

Make `qa-stack.yml` correct and give it everything its steps need, e.g.:

- **Author or repair `qa-stack.yml`** so the workflow can stand the stack up from cold: point `launch`
  at the repo's documented bring-up command (a `make dev-stack-*` target, `docker compose up -d`, a dev
  server), set a real `entry_url`/`health_path` readiness probe, and list the `prepare` (deps/build/
  migrations) and `seed` (baseline fixtures, the Auth-emulator test user) steps as ordered commands.
  Add a `stop` recipe only if the stack should be torn down; omitting it leaves an expensive shared
  stack up for reuse, which is the intended default. Set an `identity` marker so an already-serving
  stack is adopted rather than double-bound.
- **Install missing tooling**: project dependencies (`npm ci` / `pub get` / `go mod download`),
  **Playwright browsers** (`npx playwright install`), Maestro, or other QA tools the runbook names.
  Installing an absent QA tool is setup, never a "blocked" condition. (These belong as `prepare` steps
  when the stack needs them every run; run one-off host installs directly.)
- **Fix broken local config**: a wrong/missing local env file (`.env.local`, backend URL, emulator
  host/port), a stale generated client, a port collision, an un-run migration a bring-up step needs.
  Regenerate generated artifacts the stack needs.
- **Seed the baseline** as idempotent `seed` steps in the manifest — including the **test user** in the
  Auth emulator for sign-in — so the stack comes up with something to observe, deterministically.

A **foreground in-QA service** that must stay live only for the QA run (e.g. a dev server pinned to
branch source) belongs in the QA plan's `background:` block, where ostler owns it for the run — not in
your shell and not as a `launch` you leave running.

## Hard boundaries (load-bearing)

- **Never background a long-lived process in your own shell.** A service you start and leave running is
  killed at node teardown — the workflow owns stack lifecycle, not you. Durable services go in
  `qa-stack.yml` (heavyweight bring-up, run by `ensure_stack`); foreground in-QA services go in the QA
  plan's `background:` block (run by ostler). You may run a bring-up/seed command **to completion,
  bounded by a wall-clock timeout,** to prove the recipe works — a bring-up command exits 0 once its
  stack serves — but never depend on a process still alive after this node returns.
- **Do NOT modify application/product source to make QA pass.** Wiring a missing control, fixing a 500,
  correcting a label, building a missing surface or its required data binding is the **code-fix** loop's
  job (`apply-qa-fixes`), not yours. If the real problem is that the feature is broken or missing, that
  is **not** a setup problem — say so in your notes and return `ready` (so QA re-runs and routes it to
  the code-fix loop). Touch only the stack manifest, dev-environment config, tooling, and stack fixtures.
- **Do NOT disrupt unrelated services or destroy data.** Other projects' containers/emulators may be
  running on this machine. Bring up only this repo's stack; never `docker system prune`, wipe volumes,
  kill unrelated processes, or delete data to "clean up". Resolve a port collision by configuring this
  repo's port, not by killing whatever else holds it.
- Stay within MVP scope; do not provision cloud/paid infrastructure.

## Verify before you claim ready

Don't just edit the manifest — **prove its recipe works**: run the `prepare`/`seed`/`launch` commands
to completion (bounded by a timeout) and confirm the stack answers its `health` probe — the dev server
responds, the emulators are reachable, the API health endpoint returns, the test user can sign in.
Capture the proof (command output / health responses) in your report. Leave the stack however its
`stop` policy dictates; `ensure_stack` will adopt it if it is still serving, or bring it up from cold
if not — either way the manifest must be able to stand it up without you.

## Output

Write a short setup report to `{{ workhorse_var('spec_dir') }}/setup-fix.md` describing what was wrong,
what you changed/started, and the readiness proof.

Create it through `ostler` first — `timeout 30 ostler create spec <story-name> setup-fix.md`, where
`<story-name>` is the folder name of `{{ workhorse_var('spec_dir') }}` — which stamps its `type:`
frontmatter. Write the report **below the `---` block, leaving it in place**.

Then return this exact JSON object in your **final response** (after the markdown report):

```json
{
  "setup_result": {
    "status": "ready" | "unfixable",
    "notes": "What was blocking QA, what you changed/started to fix it, and the readiness proof — or, if unfixable, exactly what human-only resource (secret, deployed env, hardware) is required."
  }
}
```

- **`ready`** — the environment is now QA-capable (services up and verified, tools installed). The
  workflow re-runs QA. Also use `ready` when you conclude the blocker is **not** an environment problem
  (the feature is genuinely broken/missing) so QA re-runs and routes it to the code-fix loop.
- **`unfixable`** — the blocker genuinely needs a human: a real credential/secret that cannot be
  generated locally, a deployed/preview environment, or hardware. The workflow escalates to the
  operator. Reserve this for true walls — prefer `ready` whenever you made the stack runnable.
