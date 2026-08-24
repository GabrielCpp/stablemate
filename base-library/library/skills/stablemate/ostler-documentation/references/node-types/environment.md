# `environment`

Where a stack runs: the addresses, backing services and stack files that make "local" or
"staging" a concrete thing. Reach for `environment` when the subject is *which* system, not
how it is started — that is a [`runbook`](runbook.md), which points here with `environment:`.

## Identity

File type under `docs/features/<service>/ops/`, `type: environment` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `selector` | no | how this environment is chosen |
| `services` | no | nested; one child per service, its env-scoped URL/host |
| `backing` | no | nested; backing projects, DBs, buckets, emulators |
| `local-only` | no | `true` — tooling must refuse to target it without an override |
| `code` | no | link, **owns** its file — the stack files it materializes |
| `config` | no | **owns** the path — the configuration files the stack reads |
| `verify` | no | a check |
| `fixture` | no | a fixture |

`code:` is declared here because the QA-context mapper reads `code:` on every node type to find
a changed path's owner. Without it an environment's own compose files and emulator configs are
`unmapped-change` errors on the first packet that touches them, and the book has no lawful way
to own them.

`config:` owns like `code:` with one more effect: a declared config path is a production unit
even where the QA-context filter would drop it as stack config. Not a grounding key.

An environment states facts a plan can be held to — a pinned provider version, a backend that
is local, a service on the address the book gives — so `verify:` exists here for the same
reason it exists on a component: without it every obligation this node mints is covered by
whatever the scenario happened to assert, and the pin the program lost reads exactly like the
pin it kept.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type),
which are where an environment's claims usually live (`persistence:`, `consistency:`).

## Required sections

None.

## Relationships

Pointed at by a runbook's `environment:`. Nothing points outward from here except `code:`.

## Minimal example

```bash
timeout 30 ostler scaffold environment environment-local --service acme
```

```markdown
---
type: environment
---

# Local

- selector: the default when no environment is named
- local-only: true
- services:
  - links-api: http://127.0.0.1:8080
- backing:
  - postgres: 127.0.0.1:5432, database `links_dev`
- code: docker-compose.yml
- config: config/local.yaml
- persistence: link rows survive a stack restart
- verify: persists(subject="a link row created before the restart")
```

## Doctor codes it can trip

`runbook-local-only` (raised on the runbook that boots it), `dangling-code-ref`,
`missing-code-symbol`, `undeclared-obligation`, `weak-check`. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The bullets state what this environment is. If a reader could target the wrong one — a legacy
staging and its replacement, each right in its own context — and still satisfy every claim on
it, that belongs in a [`concept`](concept.md), pointed at with `detail:`.
