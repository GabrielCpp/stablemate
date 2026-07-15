---
agent: agent
---

# Make the Dev Environment QA-Capable — {{ repo.name | title }}

QA reported it was **blocked** — it could not exercise the story's acceptance criteria because the
**dev environment itself could not be brought up**, not because the code is wrong. Your job is to do
**anything you reasonably can to make the local dev/QA environment runnable**, so the next QA pass can
actually drive the running app. You are fixing the *setup*, not the product.

This is the alternative to giving up: an un-runnable stack (emulators down, dev server not started,
Playwright browsers missing, dependencies not installed, a broken local config, a fixture/seed the
stack needs to boot) is an **agent-fixable** problem — fix it. Only a blocker that genuinely needs a
human (a real secret/credential that cannot be generated locally, a deployed/preview environment, or
hardware) is `unfixable` → report that and the workflow escalates to the operator.

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

- `{{ workhorse_var('spec_dir') }}/qa-plan.md` — the QA runbook. Its **pre-flight** names the stack,
  services, tools, fixtures and sign-in the ACs need. That pre-flight is your checklist of what must
  be up.
- `AGENTS.md` and the project's **developer / local-stack runbook** — the documented way to stand up
  this repo's environment (the `make` targets, compose profiles, emulator/devstack start commands,
  seed/fixture commands, tool installs). **Prefer these documented commands over improvising.**
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

## What you may do (fix the environment)

Do whatever the repo's runbook and QA skills indicate is needed to make the stack QA-ready, e.g.:

- **Start the services** the QA pre-flight needs: the dev server, the backend/API, the database, the
  Firebase/Firestore/Auth/Storage emulators, the compose devstack profile — using the repo's
  documented start commands. Wait for readiness; verify they actually answer.
- **Install missing tooling**: project dependencies (`npm ci` / `pub get` / `go mod download`),
  **Playwright browsers** (`npx playwright install`), Maestro, or other QA tools the runbook names.
  Installing an absent QA tool is setup, never a "blocked" condition.
- **Fix broken local config**: a wrong/missing local env file (`.env.local`, backend URL, emulator
  host/port), a stale generated client, a port collision, an un-run migration the dev stack needs to
  boot. Regenerate generated artifacts the stack needs.
- **Seed the baseline the stack needs to come up** when the runbook defines a seed/fixture command for
  the dev environment, and create the **test user** in the Auth emulator for sign-in.

## Hard boundaries (load-bearing)

- **Do NOT modify application/product source to make QA pass.** Wiring a missing control, fixing a 500,
  correcting a label, building a missing surface or its required data binding is the **code-fix** loop's
  job (`apply-qa-fixes`), not yours. If the real problem is that the feature is broken or missing, that
  is **not** a setup problem — say so in your notes and return `ready` (so QA re-runs and routes it to
  the code-fix loop). Touch only dev-environment config, tooling, services, and stack fixtures.
- **Do NOT disrupt unrelated services or destroy data.** Other projects' containers/emulators may be
  running on this machine. Start only this repo's stack; never `docker system prune`, wipe volumes, kill
  unrelated processes, or delete data to "clean up". Resolve a port collision by configuring this repo's
  port, not by killing whatever else holds it.
- **Every command must be bounded by a wall-clock timeout** (per the repo's CLI conventions) — never
  launch an unbounded blocking process in the foreground.
- Stay within MVP scope; do not provision cloud/paid infrastructure.

## Verify before you claim ready

Don't just run start commands — **confirm the environment now answers**: the dev server responds, the
emulators are reachable, the API health endpoint returns, the test user can sign in, Playwright can
launch. Capture the proof (command output / health responses) so the re-QA can rely on it. If you
brought services up, leave them running for the QA pass.

## Output

Write a short setup report to `{{ workhorse_var('spec_dir') }}/setup-fix.md` describing what was wrong,
what you changed/started, and the readiness proof.

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
