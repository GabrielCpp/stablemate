# `environment`

Where a stack runs: the addresses, backing services and stack files that make "local" or
"staging" a concrete thing. Reach for `environment` when the subject is *which* system, not
how it is started — that is a [`runbook`](runbook.md), which points here with `environment:`.

## Identity

File type under `docs/services/<service>/ops/`, `type: environment` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `selector` | no | how this environment is chosen |
| `services` | no | nested; one child per service, its env-scoped URL/host |
| `backing` | no | nested; backing projects, DBs, buckets, emulators |
| `local-only` | no | `true` — tooling must refuse to target it without an override |
| `sharing` | no | `shared` (the default) or `per-run`: whether every run uses one stack or brings up its own copy |
| `addresses` | no | nested; one child per address a runbook reads as `{name}`: its URL when shared, what it serves when per-run |
| `variables` | no | nested; one child per variable. `NAME: value` is a literal the agent may read. `NAME: secret` is a value saddlebag holds, registered with `--tag environment=<slug> --var NAME`. Write no real value here: `ostler env exec <slug> -- CMD` supplies the held ones at run time. |
| `code` | no | link, **owns** its file — the stack files it materializes |
| `config` | no | **owns** the path — the configuration files the stack reads |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `capture` | no | a capture |
| `tests` | no | link — the test files covering it |

`addresses:` names the places a client reaches this stack, such as the gateway a browser opens.
A runbook writes `{gateway}` in its `entry-url:`, `stop:` and step commands instead of a host
and port. The bring-up reads each name from the run's address book as the command starts. A
shared environment's book is the page itself, so each entry states its URL. A `sharing:
per-run` environment gives each run its own copy on its own ports. Its entries say what each
address serves and state no URL, because no URL holds for every run. The runbook's recipe
writes the copy's book as a JSON object of name to URL at the path in
`$STABLEMATE_ADDRESS_BOOK`, and names the copy after `$STABLEMATE_LEASE`. A bring-up of a
per-run environment needs a lease: `ostler qa stack up --lease NAME`.

`code:` is declared here because the QA-context mapper reads `code:` on every node type to find
a changed path's owner. Without it an environment's own compose files and emulator configs are
`unmapped-change` errors on the first packet that touches them, and the book has no lawful way
to own them.

`config:` owns like `code:` with one more effect: a declared config path is a production unit
even where the QA-context filter would drop it as stack config. Not a grounding key.

An environment runs nothing a check can observe, so a claim on it compiles to no scenario. A
fact about where the stack runs, such as a pinned provider version or a service on the address
the book gives, goes on a [runbook](runbook.md) step whose `run:` exits non-zero when the fact
is false. Bringing the stack up then checks it. A fact about what the product does, such as a
row that survives a restart, goes with its `verify:` on the endpoint, invocation or interaction
that produces it.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).
A claim stated with one of them here compiles to no scenario, for the reason above.

## Required sections

None.

## Relationships

Pointed at by a runbook's `environment:`. Nothing points outward from here except `code:`.

The services a local copy runs, and what each needs, are not bullets on this page. They are in
the book's `stack.yml`, described in the `ostler-cli` skill's `references/stack.md`, which `ostler env` brings up one copy at a time.

A QA bring-up that is not told which environment to boot picks one itself: it narrows to the
environments declared `local-only: true` and takes the first by page path. Nothing in the book
marks the choice, because there is nothing for an author to decide — a bring-up creates and
destroys a stack, and `local-only: true` is already the claim that doing so to this one is
safe. So an environment file just states what that environment *is*: its hostnames, its
services, its backing stores.

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
```

## Doctor codes it can trip

`runbook-local-only` and `runbook-unknown-address` (raised on the runbook that boots it), `environment-address-name`, `environment-address-value`, `dangling-code-ref`,
`missing-code-symbol`, `undeclared-obligation`, `weak-check`. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The bullets state what this environment is. If a reader could target the wrong one — a legacy
staging and its replacement, each right in its own context — and still satisfy every claim on
it, that belongs in a [`concept`](concept.md), pointed at with `detail:`.
