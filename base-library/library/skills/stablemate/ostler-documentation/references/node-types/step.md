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
| `kind` | **yes** | `prepare` \| `service` \| `seed` \| `run` \| `health` \| `verify` \| `drive` |
| `run` | no | the exact bounded command |
| `working-directory` | no | cwd, when not the repo root |
| `timeout` | no | seconds; this step's own ceiling |
| `env` | no | nested; the env-var wiring this step needs |
| `health` | no | service/health steps: the real readiness signal |
| `produces` | no | run steps: output artifact path(s) or glob(s) |
| `verify` | no | **a link, not a check** — golden or deterministic output |
| `optional` | no | `true` for best-effort steps |
| `depends-on` | no | ordering hint (default: document order) |
| `provenance` | no | `derived` (build pass) \| `verified` (walkthrough) |

**`verify:` on a step is the trap.** On every normative type it is a check; here it is a
`link`. A boot step's `verify:` says how to tell *the step* ran — a golden file, a
deterministic output — which is not an observation about the product and mints no obligation.
Same word, different job. Writing a check-vocabulary call here is a category error: put
product observations on the node that makes the claim.

A `step` declares **no normative keys of its own**. It mints nothing; the runbook it belongs
to carries the contract. The
[shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type) still
apply, but they rarely belong on a boot step.

## Relationships

Ordered by document order unless `depends-on:` says otherwise. Exactly one step in a runbook
may be `kind: service`.

## Minimal example

```bash
timeout 30 ostler scaffold step serve --in docs/features/acme/ops/links-local.md
```

```markdown
### serve

- kind: service
- run: make serve
- working-directory: services/links
- env:
  - PORT: 8080
- health: GET /healthz returns 200 with "links-api" in the body
- timeout: 120
- provenance: verified
```

## Doctor codes it can trip

`missing-required-bullet` on `kind:`, `runbook-bad-kind`, and — raised against the enclosing
runbook — `runbook-incomplete` (no `kind: service` step) and `runbook-multi-service` (more
than one). See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The step states one command. If a reader could run the wrong bring-up — a legacy path and its
replacement, each right in its own context — that belongs in a [`concept`](concept.md) linked
from the runbook, not in a step.
