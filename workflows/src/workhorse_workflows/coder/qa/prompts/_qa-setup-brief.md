## The stack and setup brief

Repair the stack and its setup yourself. The goal is a stack the workflow can bring up from
cold. Never start a service and leave it running.

### How the stack comes up

The environment of this story's services declares the stack, and the workflow runs its copy
for this run under the lease `{{ lease }}`. Use the same two commands:

```bash
ostler env up --copy {{ lease }}
ostler env address <service> --copy {{ lease }}
```

`ostler env up` brings the copy up and waits until every service is ready. `ostler env address`
prints the URL the copy publishes a service at, and the plan's targets name that service as
`{<service>}`. `ostler env ls` lists the services and the copies running them. A command run
inside a service of the copy goes through `ostler env compose --copy {{ lease }} -- <args>`.

Run every `ostler book` and `ostler env` command from `{{ workhorse_var('book_root') }}`.
The stack is declared in `{{ workhorse_var('service_books') }}/<name>/ops/stack.yml`, one per service book.
`ostler env check` checks that every `stack.yml` fits together; run it after you change one.

### What to repair

- **A stale build.** The copy must build from the working tree. Bring it up again after a
  change to the product, and use `ostler env up --fresh` only when the data itself is the
  problem.
- **Missing tooling**: the repo's dependency install, a browser or device runtime a driver
  needs, a QA tool the plan names. Installing an absent tool is setup, never a block.
- **Broken local config**: a missing env file, a wrong backend URL or emulator host, a stale
  generated client, a port collision, an unapplied migration.
- **The baseline seed**: the fixture sets the environment loads. Name them with
  `--fixtures` when a claim needs one the default leaves out.

The commands come from `AGENTS.md` and the repo's local-stack notes, not from improvising.
The touched layers' QA skills say how each layer comes up:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
- **{{ r.label }}**: {{ find_by_tags("qa", r.type) | default("(none installed)", true) }}
{%- endfor %}
{%- else %}
- None resolved. Fall back to the plan's Verification Commands and its Local run (smoke).
{%- endif %}
{% if verification_setup and (verification_setup.profile or verification_setup.fixtures) %}

The surface needs the capable stack{% if verification_setup.profile %}, profile `{{ verification_setup.profile }}`{% endif %}, with its fixtures present. Bring that one up, not a thin default.
{% endif %}

### A runner requirement

A block such as `target '<name>' requires the Playwright Python package`, or one naming
ffmpeg, ffprobe, maestro or adb, comes from the QA runner's own preflight. The workflow runs
that runner inside its own interpreter, `{{ workhorse_var('runtime_python') }}`, so that is
the environment to repair. Check it the way the preflight does:
`{{ workhorse_var('runtime_python') }} -c "import playwright.sync_api"`.
The ffmpeg, ffprobe, maestro and adb requirements are `PATH` lookups from the workflow's
process. Rerun the import or `which` check after installing, and quote its output.

### Boundaries

- Never background a long-lived process. A service scoped to one QA run goes in the plan's
  `background(...)`.
- Never modify product source. A broken or missing feature is a finding, not setup.
- Never disrupt unrelated services or destroy data. Bring up only this repo's stack.
- Provision no cloud or paid infrastructure.

### Proof

`ostler env check` passes after a change to a `stack.yml`. `ostler env up --copy {{ lease }}` reports the copy serving or names the service that failed.
Quote its output. A blocker only a human can clear (a real secret, hardware) is a `blocked`.
