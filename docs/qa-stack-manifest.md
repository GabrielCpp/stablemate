# The QA stack manifest (`qa-stack.yml`)

A **stack manifest** is a per-repo, declarative recipe for standing up the QA stack — the
docker-compose services, emulators, database, and baseline seed a story's acceptance
criteria need in order to be exercised. The coder workflow's `ensure_stack` step reads it
and hands the lifecycle to `workhorse.stack`, so the stack is brought up **outside any
agent turn** and cannot be killed by node teardown mid-build.

> Deferred increments (consuming-repo manifests, epic-level teardown, re-seed skip, a `fresh`
> fingerprint helper, env-pool phase 4) are tracked in
> [qa-stack-followups.md](qa-stack-followups.md).

## Why it exists

Before this contract, a coder run brought the stack up by having the setup/implement agent
run `make dev-stack-…` (or `docker compose up`) in its own shell. A long-running process a
node backgrounds is owned by nothing: the engine reaps the node's process tree when the
node ends, and an agent turn reaps its own grandchildren between turns. So the stack was
killed in the gap between "bring it up" and "run QA" — a failure that burned three QA
attempts on a real run. Moving bring-up into a workflow-owned `script:` node driven by this
manifest removes the agent's shell from the ownership path entirely.

The manifest owns the **heavyweight** stack. A **foreground in-QA service** scoped to the
run (a dev server pinned to branch source, an event tail) belongs in the QA plan's
`background:` block, where ostler starts and reaps it for the run — not here.

## Location

`qa-stack.yml` at the repo root — the default of the coder workflow's `qa_stack_manifest` var,
which `ensure_stack` resolves against the repo root. A repo with no manifest is not an error:
`ensure_stack` reports `skip` and QA proceeds exactly as before.

**One repo, one stack, one manifest.** Keep the default. Adding a new service to a monorepo is
not a reason to add a second manifest — it is a reason to extend the one that exists, because
the new service almost certainly has to *talk* to the ones already there. Services that share an
identity plane must share the emulator that mints its tokens: a second suite on shifted ports
issues tokens the first suite's services reject, so one browser sign-in in QA authorizes a call
to `web-app` and collects a 401 from `api-service` in the same session — a stack defect wearing
a product bug's clothes. The same goes for a shared database, a shared message broker, or any
fixture two services both read. Extending the root manifest costs a few lines; splitting it
costs a class of failure that QA reports as the product's fault.

A second manifest is right only when the stacks are genuinely disjoint — nothing shared, no
service in one calling a service in the other — and the root manifest would bring up infra the
other service never touches:

```bash
workhorse run coder --params '{"qa_stack_manifest":"mobile-app/qa-stack.yml"}'
```

The path is repo-relative, and it is threaded to the `setup-fix` agent too, so the repair loop
authors the manifest at the path the run actually reads rather than at the root.

## Schema

The manifest reuses the OKF runbook `environment`/step vocabulary (`docs/okf-runbook.md`
§4.3 — `prepare`/`service`/`seed`/`health`). Top-level keys:

| Key | Meaning |
|---|---|
| `entry_url` | The base URL the stack serves; combined with `health_path` for the readiness probe. |
| `health_path` | Path appended to `entry_url` for the HTTP readiness probe (default `/`). |
| `app_cwd` | Working directory for `launch` and steps, **relative to the repo root** (default `.`). |
| `boot_timeout` | Seconds to wait for the stack to answer the probe (default 30; give a cold image build minutes). |
| `identity` | A marker string expected in the served body — the readiness signal, and a precondition for reuse (a serving stack is only a *candidate* for adoption; `reuse` decides). |
| `reuse` | When a stack already serving may be adopted instead of brought up again: `if-fresh` (default), `always`, or `never`. See **Staleness** below. |
| `fresh` | A probe command (exit 0 ⇔ the running stack reflects the current code) that gates adoption under `reuse: if-fresh`. Same string-or-mapping shape as a step. |
| `launch` | An **idempotent, self-freshening** bring-up command — e.g. `docker compose up -d --build`. It re-runs whenever the stack is not adopted, so it must be safe against an already-running stack (a cache-hit no-op on no change; a rebuild + recreate on changed code). Not a raw foreground server — those go in the QA plan's `background:` block. Optional. |
| `stop` | The teardown recipe. **Omit to leave an expensive shared stack up** (the intended default). |
| `prepare` | Ordered blocking steps run **before** `launch` (deps, build, migrations). |
| `seed` | Ordered **idempotent** steps run **after** the stack serves (baseline fixtures, the Auth-emulator test user). |
| `health` | Ordered command gates run last (e.g. a `stack-health` target); each must exit 0. |

Each `prepare`/`seed`/`health`/`fresh` entry is either a bare command string or a mapping:

```yaml
- run: make seed-users
  working-directory: api    # relative to repo root; overrides app_cwd for this step
  timeout: 120              # seconds; defaults to the step ceiling
```

## Staleness — why adoption is earned, not automatic

A container built **from the code under test** goes out of date the moment a story changes
that code, unless it is rebuilt. A stack left serving from a prior story is therefore a
*stale build*, and adopting it blindly would run QA against old code and report a false
result — the same trap that made an earlier rewrite run the web app from live source instead
of its built container snapshot. So a serving stack is adopted only when `reuse` proves it
is safe:

- **`if-fresh` (default)** — adopt only if a `fresh` probe is declared and passes; otherwise
  re-run `launch` (which rebuilds). **With no `fresh` probe, the default never adopts** — it
  always re-launches, so staleness is impossible unless you opt out. This is the right
  default for any stack that embeds the code under test.
- **`always`** — adopt whenever the identity is serving. Reserve this for a
  **code-independent** stack (a stock DB or emulator image holding fixtures) whose build does
  not depend on the code under test. This is the only case where skipping bring-up *and*
  re-seed is safe, and it is where the "leave an expensive stack up and adopt it" win lives.
- **`never`** — always re-run `launch`; never adopt.

The complementary move is to keep code-embedding services **out** of the adopted stack: run
a service that must reflect the working tree (a dev server pinned to branch source) from the
QA plan's `background:` block, where ostler starts it from source for the run so it is always
fresh. Put only durable, code-independent infra behind `reuse: always`.

## Semantics (from `workhorse.stack`)

- **Reuse decision.** When `identity` is serving, `ensure_stack` consults `reuse`/`fresh`
  (above). If it adopts, `prepare`/`launch`/`seed` do **not** re-run and nothing is
  double-bound. If it does not, it re-runs `launch` to refresh the stack against current
  code, then `seed`/`health`.
- **Bring-up vs foreground, told apart by behavior.** A *bring-up command*
  (`make dev-stack-test-db`, `docker compose up -d --build`) exits 0 once the stack serves in
  containers this process does not own — a clean exit is **not** death, so `ensure_stack`
  keeps polling health to the deadline. (A foreground server that stays alive is handled too,
  but such services belong in the QA plan's `background:` block, not here.)
- **Leave-up policy.** With no owned process group and no `stop` recipe, teardown leaves the
  stack running on purpose — an expensive shared stack is cheaper to leave up for the next
  story to adopt (under `reuse: always`) than to rebuild.

## Relationship to `qa_stack` and the QA plan

- The story-level **`qa_stack`** object (authored in the story's `## Verification setup`,
  carried through plan → implement → qa) is a *descriptor*: the profile and fixtures a
  surface needs, in prose. `qa-stack.yml` is the *executable* recipe the workflow runs. When
  the implement step discovers the bring-up/seed commands, it records them here so QA reuses
  exactly what it ran.
- The QA plan (`qa-plan.yml`) assumes the heavyweight stack is already serving. It declares
  only foreground in-QA services in its `background:` block; it never brings the stack up.

## Example

The API is built from code the coder changes, so its stack is refreshed every story via a
self-freshening `launch` (docker rebuilds only the changed image); the default `reuse:
if-fresh` with no `fresh` probe never adopts it stale:

```yaml
# qa-stack.yml — acme's api-service QA stack
entry_url: http://localhost:8080
health_path: /healthz
app_cwd: api
boot_timeout: 900          # cold build: docker image builds + emulator start
identity: "acme-api"       # served by /healthz — the readiness marker
launch: docker compose up -d --build    # self-freshening: rebuilds the changed image, recreates its container
stop: docker compose down               # omit to leave the stack up between stories
seed:
  - make seed-emulator                  # idempotent: baseline fixtures + the sign-in test user
health:
  - make stack-health                   # a real readiness gate, not a shell served with the API down
```

For a stack whose bring-up is expensive **and** code-independent (a stock DB/emulator holding
a large fixture set, no app image built from source), declare `reuse: always` so it is
adopted across stories and the costly re-seed is skipped — and run the code-under-test as a
live `background:` service in the QA plan:

```yaml
# qa-stack.yml — code-independent fixture stack, safe to adopt
entry_url: http://localhost:9099        # the emulator/DB, not an app built from source
identity: "emulator-ok"
reuse: always                           # code-independent → adopt the serving stack, skip re-seed
launch: make dev-stack-db
seed:
  - make seed-emulator                  # only runs on a cold bring-up, not on adopt
```

If a code-embedding stack is expensive to rebuild, keep `reuse: if-fresh` and add a `fresh`
probe so it is adopted while the code is unchanged and rebuilt the moment it drifts:

```yaml
reuse: if-fresh
fresh: make stack-matches-head          # exit 0 ⇔ running images built from current source
```
