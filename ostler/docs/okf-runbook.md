# The operational profile — `runbook`, `environment`, `step`

Status: **implemented** — `ostler/registry.py` (the types), `ostler/qa/runbook.py` (the
reader), `ostler/doctor.py::_check_runbook` (the linter), `ostler qa stack up|down` (the CLI).

The OKF describes what a system *is*: screens, servers, concepts, flows. This profile
describes how it is *run* — what brings it up, where it then answers, and how you can tell.
It exists because the coder QA lane needs that answer before it can test anything, and for a
long time it looked for the answer in a `qa-stack.yml`: a root file with no schema, no
validator, no scaffold, and two authors — a plan-gated prompt line a greenfield story never
reaches, and a repair prompt reached only *after* QA had already run against nothing. The
declaration is documentation about the system, so it belongs in the book with everything else
that is.

## 1. The three types

| type | kind | context | what it says |
| --- | --- | --- | --- |
| `runbook` | file | `ops` | how one stack is brought up, and how you know it is up |
| `environment` | file | `ops` | where it points once it is: services, backing stores, blast radius |
| `step` | section | — | one ordered boot step, under a runbook's `## Steps` |

A runbook is not a product surface, which is what lets it own an executable recipe. The
ownership gate (`ostler/qa/context.py`) refuses to let a *feature* Concept own a stack
manifest for exactly that reason — a bring-up is not something a user observes — and the `ops`
context is the place that objection points to.

### 1.1 Where they live

Under the features doc root, in the service's `ops/` directory, which is where
`ostler scaffold` puts them:

```
docs/features/<service>/ops/local.md      (type: environment)
docs/features/<service>/ops/qa-stack.md   (type: runbook)
```

## 2. `runbook`

Required: `driver:`, and a `## Steps` section.

```markdown
---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- environment: [local](local.md)
- surfaces: [Sign in](../ui/sign-in.md)
- code: `cmd/server/main.go::main`
- entry-url: http://localhost:8080
- health-path: /healthz
- identity: `"service": "api"`
- reuse: if-fresh
- fresh: git diff --quiet HEAD -- app/
- boot-timeout: 120
- health-timeout: 30
- stop: docker compose down -v
- working-directory: app
- secrets:
  - QA_TOKEN: ./scripts/mint-token.sh
```

| bullet | meaning |
| --- | --- |
| `driver` | `web` \| `mobile` \| `http` \| `cli` \| `artifact` \| `iac` \| `none` — how this surface is exercised once it is up |
| `environment` | link to the `environment` node this boots (default: the local one) |
| `cli` / `surfaces` / `code` | links: the dev CLI it drives with, the nodes it exposes, its launch entry point |
| `entry-url` | base of the HTTP readiness probe, and the URL QA opens |
| `health-path` | joined onto `entry-url` (default `/`) |
| `identity` | a substring of the health *body* proving the thing answering is ours, not a stale server on the same port |
| `reuse` | `if-fresh` (default) \| `always` \| `never` — whether an already-serving stack may be adopted |
| `fresh` | a command exiting 0 iff a serving stack reflects current code; consulted under `if-fresh` |
| `boot-timeout` | seconds; ceiling on bring-up |
| `health-timeout` | seconds; one window shared by every health gate |
| `stop` | teardown recipe; **absent means leave it running**, which for a shared emulator is the cheaper policy |
| `working-directory` | cwd for the launch and for every step that does not override it, repo-relative |
| `secrets` | one child per credential, `NAME: <shell that prints it>` — see §5 |

### 2.1 How a value is read

A backticked value is the value and the rest of the line is commentary; unbackticked, the
first line is all of it. `` - identity: `"status": "ok"` — the health body `` and
`- identity: "status": "ok"` therefore mean the same thing, and a bullet may be documented
in place. This is the same reading okf-builder's walkthrough has always applied to the
`server` contract (§6); one book must not mean two things to two readers.

Everything repo-relative comes back absolute from the reader. Nothing downstream resolves
paths, so an unresolved `.` would launch the stack from whatever cwd the engine happened to
hold.

## 3. `environment`

```markdown
---
type: environment
title: local
---

# local

- selector: local
- services:
  - api: http://localhost:8080
  - web: http://localhost:5173
- backing:
  - postgres: docker compose service `db`, dropped and reseeded on every bring-up
- local-only: true
```

`local-only: true` says this recipe is destructive and belongs on a laptop. A runbook that
boots a `local-only` environment whose `services:` name a host that is not this machine is a
`doctor` error: honouring it is free at author time and impossible at run time, because by
then the recipe is already talking to whatever it was pointed at. The evidence is the service
*host*, never the `selector:` — a selector is free prose (an env-var assignment, a profile
name, a sentence), so reading intent out of it would both miss `prod-eu` and libel
`APP_BIND=127.0.0.1`.

## 4. `step`

A `### <id>` under the runbook's `## Steps`. Document order is execution order.

```markdown
## Steps

### build

- kind: prepare
- run: docker compose build
- timeout: 600

### serve

- kind: service
- run: docker compose up -d --wait
- health: curl -fsS http://localhost:8080/healthz

### seed

- kind: seed
- run: ./scripts/seed.sh
- env:
  - SEED_PROFILE=qa
```

### 4.1 `kind:`

| kind | phase | when it runs |
| --- | --- | --- |
| `prepare` | `prepare` | before launch — builds, migrations, dependency installs |
| `service` | `launch` | **exactly one per runbook**: the command that starts the system |
| `seed` | `seed` | after the stack answers: fixtures, accounts, sample data |
| `health` | `health` | a readiness gate beyond the HTTP probe |
| `run` / `verify` / `drive` | — | exercise the system once it is up. **Not** bring-up phases: that is the QA plan's job, and the reader skips them |

### 4.2 The other bullets

`run:` is the exact bounded command. `working-directory:` overrides the runbook's, repo-relative.
`timeout:` is this step's own ceiling in seconds. `optional: true` makes a step best-effort —
carried into the recipe itself, since the runner has no soft mode. `health:` on the `service`
step is the real readiness signal and becomes a health gate. `env:` children are ordinary shell
assignments (`PORT=8080`, `TOKEN=$(scripts/mint.sh)`) prefixed onto the command — the step
already runs through `bash -c`, and a second syntax for the same thing buys nothing.

### 4.3 What the reader produces

The runbook's scalars plus its steps fold into the manifest `ostler.qa.stack.ensure_stack`
takes: `entry_url`, `health_path`, `identity`, `reuse`, `fresh`, `boot_timeout`,
`health_timeout`, `stop`, `app_cwd`, `repo_root`, `launch`, and the `prepare` / `seed` /
`health` step lists. Every step is emitted in mapping form (`{run, working-directory,
timeout}`) and never as a bare string, because the runner gives a bare string the *boot*
timeout and a mapping the much larger step timeout — an asymmetry an author should never have
to meet.

## 5. `secrets:` — freshened per run, not per bring-up

A short-lived credential minted while the stack booted is already stale by the lap that spends
it, and the bring-up phases run once per stack while a QA plan may run many times against it.
So `secrets:` is read separately and minted immediately before each run. The recipe is
repo-owned shell that prints the secret and nothing else; nothing interprets it here, and the
value never enters a checkpoint, a `--param`, or telemetry.

Wiring that is *not* a secret — a port, a profile, a fixture path — is a step's `env:` instead.

## 6. The `server` fallback

okf-builder's walkthrough has read a thinner version of this contract off an OKF `server` node
since it was written: `launch:`, `entry-url:`, `health-path:`, `working-directory:`,
`identity:`, `stop:`, `boot-timeout:`, on the one server marked `walkthrough: true`. Those
bullets are registered on the `server` type and read by the same reader, so a book with no
runbook still yields a stack, and the walk and the QA lane share one derivation. Marking more
than one server resolves to *no* contract rather than an arbitrary pick — a walk against the
wrong service is worse than a walk that says it has nowhere to go.

## 7. What `doctor` reports

| code | severity | when |
| --- | --- | --- |
| `runbook-missing` | warn | no runbook and no walkthrough server: the book does not say how this system comes up |
| `runbook-bad-kind` | error | a `kind:` outside §4.1 |
| `runbook-bad-reuse` | error | a `reuse:` outside `if-fresh`/`always`/`never` |
| `runbook-incomplete` | error | no `kind: service` step, or nothing proving readiness (neither `entry-url:` nor a service `health:`) |
| `runbook-multi-service` | error | more than one `kind: service` step — the reader takes the first, so which one launched is otherwise luck |
| `runbook-local-only` | error | boots a `local-only: true` environment whose `services:` point off this machine |

`runbook-missing` is a warning, not an error: a book that documents a library, a CLI, or a
surface nobody serves has nothing to bring up and is not broken. Its job is to move the
discovery of an *undeclared* stack to author time, where the remedy is one node — instead of
to the middle of a QA run, where it used to arrive as a pass against nothing.

## 8. The CLI

The nodes scaffold like every other registered type — no special-casing, because the registry
is what both the scaffolder and the reader read:

```bash
ostler scaffold environment local --service api      # docs/features/api/ops/local.md
ostler scaffold runbook qa-stack --service api       # docs/features/api/ops/qa-stack.md
ostler scaffold step serve --in api/ops/qa-stack.md  # a `### serve` under its `## Steps`
```

A freshly scaffolded runbook is `runbook-incomplete` until it has a `kind: service` step and
something proving readiness. That is the point: the stub is the shape, `doctor` is the
checklist, and both arrive at author time rather than mid-QA.

```bash
ostler qa stack up              # bring the declared stack to ready
ostler qa stack up --json       # + the manifest it derived, for a repair loop to read
ostler qa stack down            # run the book's `stop:` recipe, if it has one
ostler qa stack up --runbook release   # when the book carries more than one
```

`up` adopts an already-serving stack when `reuse:` allows and it proves fresh, and reports
`status: none` when the book declares no stack at all. `down` rather than `stop`, because
`ostler qa stop` already means "kill this session's daemons" and a verb that means two
lifecycles in one namespace is a verb somebody eventually spends on the wrong one.
