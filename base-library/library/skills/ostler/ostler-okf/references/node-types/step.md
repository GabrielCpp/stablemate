# `step`

One ordered boot step of a [`runbook`](runbook.md): a single bounded command in the sequence
that brings a stack up. Reach for `step` only inside a runbook — a product action a person
takes is an [`interaction`](interaction.md), and a machine-driven one is an
[`invocation`](invocation.md).

## Identity

Section type. A `### <id>` under the runbook's `## Steps` heading. Its id is `path#anchor`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `kind` | **yes** | `prepare` \| `service` \| `seed` \| `run` \| `health` \| `verify` \| `probe` \| `serve` \| `borrow` \| `release` \| `observe` \| `drive` \| `teardown`. A `probe` belongs on a fixture step, where it asks whether the stack has a capability. A `serve` belongs on a scenario fixture step, where it starts a process the scenario talks to and the harness stops it when the scenario ends. `borrow` and `release` belong on a fixture step, where they take a thing from a resource and give it back. `observe` belongs on a resource page's `## Observations`, and a `probe` on its `## Probe`. |
| `code` | no | link, **owns** its file — the implementation this step exercises |
| `run` | no | the exact bounded command |
| `sign-in-as` | no | the saddlebag role this step signs in as; the secret carries the tag `role=<value>` |
| `working-directory` | no | cwd, when not the repo root — or `scenario:`, on a **fixture** step only, for that scenario's own directory |
| `timeout` | no | seconds; this step's own ceiling |
| `env` | no | nested; the env-var wiring this step needs |
| `health` | no | service/health steps: the real readiness signal |
| `produces` | no | run steps: output artifact path(s) or glob(s) |
| `verify` | no | **a link, not a check** — golden or deterministic output |
| `optional` | no | `true` for best-effort steps |
| `depends-on` | no | ordering hint (default: document order) |
| `open` | no | **fixture steps only**: a link to the `screen` a browser opens, by its route |
| `on` | no | **fixture steps and resource steps**: the [`resource`](resource.md) the step acts on, as a link to its page or its bare stem. An `on:` that resolves to no `resource` page is `unresolved-relation`. |
| `request` | no | `<METHOD> <path>` sent to the `http` resource named by `on:`. METHOD is one of `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, and the path starts with `/`. |
| `body` | no | A JSON object the `request:` sends. It may carry `$NAME` for facts in the step's environment and `@<fixture>.<key>` references. |
| `arrange` | no | **fixture steps only**: one browser act (`click`, `fill`, `press`, `select`) per bullet, performed in order after `open:` |

**`open:` and `arrange:` make a fixture step a browser step.** The scenario's own browser
performs it, in place of `run:`, and keeps the session it leaves. A step has one performer, so
it states either `run:` or the browser keys, never both, and at most one `open:`. A runbook
step never states them:
bring-up runs before any scenario has a browser. See
[fixture.md](fixture.md#signing-a-browser-in).

### Acting on a resource

A step with `on:` acts on a [`resource`](resource.md) through its reach. On an `http` resource
the step states `request:` and no `run:`. On a `cli` resource it states `run:`, and the harness
checks the resource's `binary:` and `secrets:` first. A step with `request:` has `on:`, and a
step with `on:` has `request:` or `run:`. A `request:` on a `cli` resource, and a `run:` on an
`http` resource, are `step-reach-mismatch`.

`kind: borrow` and `kind: release` each have `on:`. A `borrow` runs in order like any other
step, and a fact it prints is readable through `provides:` the same way. A `release` does not
run in order. The harness registers it and runs it when the scenario ends, however the scenario
ended: passed, failed or errored, and from the parent process when the scenario timed out.
Releases run in reverse order, and a release that fails never stops the others. A failed release
fails a scenario that had passed.

A release sees the fixture's facts as they stand when the scenario ends, so a fact a later step binds is in reach too. A
`DELETE /leases/$lease` reads `$lease` only when the `borrow` or an earlier step provides it.
The harness logs a request as `METHOD url` only, so no header value and no secret-bearing body
reaches a transcript.

The first step or observation on a resource runs its probe, once per harness process. See
[resource.md](resource.md#probe).

**`verify:` on a step is the trap.** On every normative type it is a check; here it is a
`link`. A boot step's `verify:` says how to tell *the step* ran — a golden file, a
deterministic output — which is not an observation about the product and mints no obligation.
Same word, different job. Writing a check-vocabulary call here is a category error: put
product observations on the node that makes the claim.

**`run:` and `health:` take a shell command, never a check expression.** `ensure_stack` (and
the fixture harness, for a `fixture`'s own steps) hands each one to `bash -c` verbatim; neither
is parsed against the `verify:` grammar. Something in the shape of `http_status(200,
path="/healthz")` reads like the checks written under `verify:` elsewhere in the book, but it
is not a command bash can run — it is a check call, and writing one here only replaces a green
`launch` phase with a bash syntax error one stage later, at bring-up time rather than at review
time. Write a real command that exits non-zero on failure instead: a `curl -fsS <url>` for a
health gate, or whatever program this step actually needs to run. If what you have in hand is
a check on the *product* — "the widget list shows the seeded row" — it does not belong on a
boot step at all; put it under the `verify:` of the claim (a `screen`'s `visible(...)`, an
`http`'s `http_status(...)`) that the check actually observes. The doctor's
`check-expression-as-command` catches the mistake before bring-up ever runs.

The same holds for prose. "exits 0 and prints the usage banner" is a description of a check,
not a command, and bash refuses it or runs its first word as a program. Describe what the
step proves in the step's body, and keep the bullet to the command itself. The doctor's
`unparsable-command` refuses a `run:`/`health:` value bash cannot parse.

**`working-directory: scenario:` is a fixture-only frame, not a path.** A `fixture` step
runs inside a scenario, so the token stands for that scenario's own directory — the same
directory `qa.tool(...).run(..., cwd=qa.scenario_checkout_copy())` runs a compiled CLI call in, so a
fixture and the command it arranges for land in one place instead of racing over the
checkout root. That directory starts as a fresh copy of the checkout as the runbook left
it. A command that only works from the checkout finds its code there, and the files it
writes stay apart from every other scenario's. A **runbook** step has no such frame: it runs at bring-up, before any
scenario exists, so the same token there names nothing and trips the doctor's
`runbook-scenario-frame`. Every other `working-directory:` value, on either kind of step,
keeps its ordinary checkout-relative meaning.

A `step` declares **no normative keys of its own**. It mints nothing; the runbook it belongs
to carries the contract. The
[shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type) still
apply, but they rarely belong on a boot step.

## Relationships

Ordered by document order unless `depends-on:` says otherwise. Exactly one step in a runbook
may be `kind: service`.

## Minimal example

```bash
timeout 30 ostler scaffold step serve --in docs/services/acme/ops/links-local.md
```

```markdown
### serve

- kind: service
- run: make serve
- working-directory: services/links
- env:
  - PORT: 8080
- health: curl -fsS http://localhost:8080/healthz | grep -q links-api
- timeout: 120
```

## Doctor codes it can trip

`missing-required-bullet` on `kind:`, `runbook-bad-kind`, `check-expression-as-command` (a
`run:`/`health:` value that parses as a check call), `unparsable-command` (a `run:`/`health:`
value bash cannot parse), `runbook-scenario-frame` (a
**runbook** step's `working-directory:` states the fixture-only `scenario:` token),
`browser-step-outside-fixture` (a **runbook** step states `open:` or `arrange:`), `step-request-shape`, `step-reach-mismatch`, and —
raised against the enclosing runbook — `runbook-incomplete` (a runbook that brings a stack up with no `kind: service` step) and
`runbook-multi-service` (more
than one). See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The step states one command. If a reader could run the wrong bring-up — a legacy path and its
replacement, each right in its own context — that belongs in a [`concept`](concept.md) linked
from the runbook, not in a step.
