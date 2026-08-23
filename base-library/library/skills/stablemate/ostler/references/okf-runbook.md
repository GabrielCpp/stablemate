# The operational profile — how a stack is declared

The OKF describes what a system *is*. Three `ops`-context types describe how it is *run*, and
they are what the coder QA lane brings a stack up from. Before them the answer lived in a
`qa-stack.yml`: a root file with no schema, no validator and no scaffold, authored only by a
repair prompt reached *after* QA had already run against nothing.

| type | kind | where |
| --- | --- | --- |
| `runbook` | file | `docs/features/<service>/ops/<name>.md` — how one stack comes up |
| `environment` | file | `docs/features/<service>/ops/<name>.md` — where it points once it is up |
| `step` | section | a `### <id>` under the runbook's `## Steps` |

## Scaffold it, do not hand-write it

```bash
ostler scaffold environment local --service api
ostler scaffold runbook qa-stack --service api
ostler scaffold step serve --in api/ops/qa-stack.md
ostler doctor            # the checklist for what you just stubbed
ostler qa stack up       # the proof it works; `--json` prints the derived manifest
ostler qa stack down
```

## The runbook

Required: `driver:` and a `## Steps` section holding **exactly one** `kind: service` step.

That service step (or an `entry-url:`/`launch:` scalar) is also what makes this runbook *the
stack*. `runbook` is the general ops type, so a procedure that starts nothing — "rotate the
keys", "preview the plan" — is a perfectly good runbook that the checks below never touch
and `ostler qa stack up` never picks.

```markdown
---
type: runbook
title: QA stack
---
# QA stack

- driver: web
- environment: [local](local.md)
- entry-url: http://localhost:8080
- health-path: /healthz
- identity: `"service": "api"`
- reuse: if-fresh
- fresh: git diff --quiet HEAD -- app/
- boot-timeout: 120
- working-directory: app
- secrets:
  - QA_TOKEN: ./scripts/mint-token.sh

## Steps

### build
- kind: prepare
- run: docker compose build
- timeout: 600

### serve
- kind: service
- run: docker compose up -d --wait
- health: curl -fsS http://localhost:8080/healthz
```

- `identity:` is a substring of the health **body**, not a host:port. It is what stops a stale
  server on the same port from being mistaken for ours.
- `reuse:` is `if-fresh` (default) | `always` | `never`. Pick `never` when the app is bind-mounted
  or rebuilt per trial — adopting a running stack then tests the *previous* code.
- `stop:` absent means leave it running, which for a shared emulator is the cheaper policy.
- A backticked value is the value and the rest of the line is commentary, so a bullet can be
  documented in place.
- Everything repo-relative comes back absolute from the reader; nothing downstream resolves paths.

### `kind:`

`prepare` (before launch) · `service` (**exactly one**, the command that starts it) · `seed`
(after it answers) · `health` (a readiness gate beyond the HTTP probe). `run`/`verify`/`drive`
are not bring-up phases — that is the QA plan's job, and the reader skips them.

A step's `env:` children are ordinary shell assignments prefixed onto the command. Use them for
wiring — a port, a profile, a fixture path. A **credential** goes in the runbook's `secrets:`
instead: those are minted immediately before each QA run rather than once at bring-up, because a
short-lived token minted while the stack booted is already stale by the lap that spends it.

## What `doctor` says

`runbook-missing` (warn) — no runbook declares a stack · `runbook-incomplete` — a stack runbook
with no `kind: service` step, or nothing proving readiness · `runbook-multi-service` · `runbook-bad-kind` ·
`runbook-bad-reuse` · `runbook-local-only` — boots a `local-only: true` environment whose
`services:` point off this machine.

`runbook-missing` is a warning because a library or a CLI has nothing to bring up. Its job is to
surface an *undeclared* stack at author time, where the remedy is one node — instead of in the
middle of a QA run, where it used to arrive as a pass against nothing.

The full spec, including the manifest mapping and the `server` fallback the okf-builder
walkthrough shares, is `ostler/docs/okf-runbook.md`.
