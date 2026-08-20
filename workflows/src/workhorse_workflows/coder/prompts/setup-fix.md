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
workflow owns stack lifecycle through a declarative **stack manifest**
(`{{ workhorse_var('stack_manifest') }}`); your job is to make that manifest and the things it needs
correct, then hand back. Concretely, the fixable problems
are: a missing or wrong manifest, a bring-up/seed/health command in it that fails, missing
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

- `{{ workhorse_var('stack_manifest') }}` (repo-relative; if present) — the **stack manifest** the
  workflow's `ensure_stack` step runs. **This exact path is the one it reads**, so author or repair it
  here — a manifest written anywhere else is invisible and the stack stays down. It declares `entry_url`/`health_path`, `launch` (the bring-up or foreground command),
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
  which tool drives it:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
  - **{{ r.label }}**: {% for s in (r.qa_skills if r.qa_skills else [r.qa_skill]) %}`{{ s }}`{% if not loop.last %}, {% endif %}{% endfor %}
{%- endfor %}
{%- else %}
  - _(none resolved — fall back to the plan's Verification Commands / Local run (smoke))_
{%- endif %}
{% if verification_setup and (verification_setup.profile or verification_setup.fixtures) %}
- The **capable stack** the surface needs: {% if verification_setup.profile %}profile `{{ verification_setup.profile }}`{% endif %}
  with its fixtures present. Bring **that** stack up — not a thin/empty default.
{% endif %}

## What you may do (make the stack bring-up-able)

Make the manifest correct and give it everything its steps need, e.g.:

- **Author or repair `{{ workhorse_var('stack_manifest') }}`** so the workflow can stand the stack up
  from cold: point `launch`
  at an **idempotent, self-freshening** bring-up command — whichever one this repo documents, and
  the variant of it that *rebuilds* — set a real `entry_url`/`health_path` readiness probe, and
  list the `prepare` (deps/build/migrations) and `seed` (baseline fixtures, the Auth-emulator test
  user) steps as ordered commands. Add a `stop` recipe only if the stack should be torn down; omitting
  it leaves an expensive stack up for reuse.
- **Do not let QA run against a stale build.** An image or bundle built from the code under test goes
  out of date the moment a story changes that code. So the manifest's `launch` must *rebuild* — a
  bring-up that reuses a previously built artifact is the bug — and adoption is governed by `reuse`:
  the default `if-fresh` with no `fresh` probe never adopts a serving stack — it re-runs `launch`.
  Only mark a stack `reuse: always` when it is **code-independent** (a stock DB/emulator with
  fixtures). A service that must reflect the working tree belongs in the QA plan's `background:` block
  (run live from source), not adopted here.
- **Install missing tooling**: this repo's own dependency-install command, the browser/device
  runtimes a QA driver needs, or any other QA tool the runbook names — with the command the runbook
  or the tool's own documentation gives.
  Installing an absent QA tool is setup, never a "blocked" condition. (These belong as `prepare` steps
  when the stack needs them every run; run one-off host installs directly.)

- **Fix broken local config**: a wrong/missing local env file (`.env.local`, backend URL, emulator
  host/port), a stale generated client, a port collision, an un-run migration a bring-up step needs.
  Regenerate generated artifacts the stack needs.
- **Seed the baseline** as idempotent `seed` steps in the manifest — including the **test user** in the
  Auth emulator for sign-in — so the stack comes up with something to observe, deterministically.

### When the block names a *runner* requirement, repair the copy the runner actually uses

A block phrased as `target '<name>' requires the Playwright Python package` (or naming ffmpeg,
ffprobe, maestro, adb) comes from the QA runner's own pre-flight, `check_runtime_requirements`. It
runs **inside the Python interpreter executing this workflow** — the QA stage imports the runner as a
library, it does not shell out to an `ostler` binary — so that is the environment to repair:

- **The interpreter is `{{ workhorse_var('runtime_python') }}`.** Check it the way the pre-flight
  does: `{{ workhorse_var('runtime_python') }} -c "import playwright.sync_api"`. If that fails, the
  run stays blocked no matter what any other Python on this machine has installed.
- **`uv tool install --force 'ostler[qa]'` repairs a *different* copy** — and so does `pip install`
  under a bare `python`, or anything run inside the project's own venv. Every one of those can
  succeed while the block comes back word-for-word identical. That is what makes this failure
  expensive: the install genuinely worked, just not where the runner looks.
- The `ffmpeg` / `ffprobe` / `maestro` / `adb` requirements are `PATH` lookups from that same
  process, so they must be on the `PATH` this workflow runs with — not only inside a container or a
  login shell profile.
- **Prove it the way the pre-flight will**: re-run the `import` (or `which`) check above after
  installing, and paste its output into your report. A package manager saying "installed
  successfully" is not the check that failed.

A repeat is not retried. If the next run comes back blocked on exactly the requirements you were
asked to fix here, the workflow stops and asks an operator instead of giving you another turn — so
verifying against the interpreter above is the whole job, not a formality.

A **foreground in-QA service** that must stay live only for the QA run (e.g. a dev server pinned to
branch source) belongs in the QA plan's `background:` block, where ostler owns it for the run — not in
your shell and not as a `launch` you leave running.

## Hard boundaries (load-bearing)

- **Never background a long-lived process in your own shell.** A service you start and leave running is
  killed at node teardown — the workflow owns stack lifecycle, not you. Durable services go in the
  stack manifest (heavyweight bring-up, run by `ensure_stack`); foreground in-QA services go in the QA
  plan's `background:` block (run by ostler). You may run a bring-up/seed command **to completion,
  bounded by a wall-clock timeout,** to prove the recipe works — a bring-up command exits 0 once its
  stack serves — but never depend on a process still alive after this node returns.
- **Do NOT modify application/product source to make QA pass.** Wiring a missing control, fixing a 500,
  correcting a label, building a missing surface or its required data binding is the **code-fix** loop's
  job (`apply-qa-fixes`), not yours. If the real problem is that the feature is broken or missing, that
  is **not** a setup problem — say so in your notes and return `ready` (so QA re-runs and routes it to
  the code-fix loop). Touch only the stack manifest, dev-environment config, tooling, and stack fixtures.
- **Do NOT disrupt unrelated services or destroy data.** Other projects' containers/emulators may be
  running on this machine. Bring up only this repo's stack; never run a machine-wide prune, wipe
  volumes, kill unrelated processes, or delete data to "clean up". Resolve a port collision by configuring this
  repo's port, not by killing whatever else holds it.
- Stay within MVP scope; do not provision cloud/paid infrastructure.

## Verify before you claim ready

Don't just edit the manifest — **prove its recipe works**: run the `prepare`/`seed`/`launch` commands
to completion (bounded by a timeout) and confirm the stack answers its `health` probe — the dev server
responds, the emulators are reachable, the API health endpoint returns, the test user can sign in.
Capture the proof (command output / health responses) in your report. Leave the stack however its
`stop` policy dictates; `ensure_stack` will adopt it if it is still serving, or bring it up from cold
if not — either way the manifest must be able to stand it up without you.

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

   `<type>` is `fix` for the stack manifest and the scripts it names, and `docs` for the
   report — two commits when you wrote both. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Output

Write a short setup report to `{{ workhorse_var('spec_dir') }}/setup-fix.md` describing what was wrong,
what you changed/started, and the readiness proof.

Create it through `ostler` first — `timeout 30 ostler create spec <story-name> setup-fix.md`, where
`<story-name>` is the folder name of `{{ workhorse_var('spec_dir') }}` — which stamps its `type:`
frontmatter. Write the report **below the `---` block, leaving it in place**.

Then return this exact JSON object in your **final response** (after the markdown report):

```json
{
  "status": "ready" | "unfixable",
  "notes": "What was blocking QA, what you changed/started to fix it, and the readiness proof — or, if unfixable, exactly what human-only resource (secret, deployed env, hardware) is required."
}
```

- **`ready`** — the environment is now QA-capable (services up and verified, tools installed). The
  workflow re-runs QA. Also use `ready` when you conclude the blocker is **not** an environment problem
  (the feature is genuinely broken/missing) so QA re-runs and routes it to the code-fix loop.
- **`unfixable`** — the blocker genuinely needs a human: a real credential/secret that cannot be
  generated locally, a deployed/preview environment, or hardware. The workflow escalates to the
  operator. Reserve this for true walls — prefer `ready` whenever you made the stack runnable.
