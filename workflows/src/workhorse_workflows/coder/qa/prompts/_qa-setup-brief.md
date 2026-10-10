## The stack and setup brief

Hand this section to the stack and setup repairer. Its job is to make the stack
bring-up-able by the workflow, so the next `ostler qa stack up` stands it up from cold. It
never starts a service and leaves it running.

### What it repairs

- **The book's runbook node**, `docs/features/<service>/ops/qa-stack.md`, which the workflow
  reads through `ostler qa stack up`. `ostler doctor` reports `runbook-missing` when it is
  absent, and `ostler scaffold runbook qa-stack --service <service>` writes the stub. Its
  bullets are `driver`, `entry-url`, `health-path`, `identity`, `reuse`/`fresh`,
  `boot-timeout`, `health-timeout` and an optional `stop`. Its `## Steps` section holds the
  ordered boot steps, each a `### <id>` with `kind: prepare | service | seed | health` and a
  `run:`. The full spec is `ostler/docs/okf-runbook.md`. A recipe written anywhere else is
  invisible to the workflow.
- **A stale build.** The `service` step must rebuild from the working tree. The default
  `reuse: if-fresh` with no `fresh` probe never adopts a serving stack. Mark `reuse: always`
  only for a code-independent stack: a stock database or emulator with fixtures.
- **Missing tooling**: the repo's dependency install, a browser or device runtime a driver
  needs, a QA tool the runbook names. Installing an absent tool is setup, never a block. A
  tool the stack needs every run is a `prepare` step.
- **Broken local config**: a missing env file, a wrong backend URL or emulator host, a stale
  generated client, a port collision, an unapplied migration.
- **The baseline seed**: idempotent `kind: seed` steps, including the test user for sign-in.

The commands come from `AGENTS.md` and the repo's local-stack runbook, not from improvising.
`qa-plan.md`'s preflight is the checklist of what the stack must serve. The touched layers'
QA skills say how each layer comes up:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}
- **{{ r.label }}**: {% for s in (r.qa_skills if r.qa_skills else [r.qa_skill]) %}`{{ s }}`{% if not loop.last %}, {% endif %}{% endfor %}
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
`uv tool install --force 'ostler[qa]'`, a `pip install` under a bare interpreter, and an
install in the project's venv each repair a different copy, and each can succeed while the
block comes back unchanged. The ffmpeg, ffprobe, maestro and adb requirements are `PATH`
lookups from the workflow's process. Rerun the import or `which` check after installing, and
quote its output.

### Boundaries

- Never background a long-lived process. Durable services go in the runbook node, and a
  service scoped to one QA run goes in the plan's `background(...)`. A bring-up command may
  run to completion under a timeout to prove the recipe.
- Never modify product source. A broken or missing feature is a finding, not setup.
- Never disrupt unrelated services or destroy data. Bring up only this repo's stack, and
  resolve a port collision by configuring this repo's port.
- Provision no cloud or paid infrastructure.

### Proof

`ostler qa stack up` runs what the workflow will run, off the node as written, so it is the
check: it reports the stack serving or names the step that failed. Run `ostler doctor` too.
Quote both outputs. A blocker only a human can clear (a real secret, a deployed
environment, hardware) is the owner's `blocked`.
