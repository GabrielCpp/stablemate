# `flow`

An end-to-end path through the system: the ordered walk from a starting condition to an
observable outcome. Reach for `flow` when the thing worth recording is a *sequence across
nodes* that no single node holds.

Not a flow: the boot sequence of a stack — that is a [`runbook`](runbook.md) and its
[`step`](step.md) children. Not a flow: a single control's behaviour, which is an
[`interaction`](interaction.md).

## Identity

File type under `docs/features/<service>/flows/`, `type: flow` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `start` | no | **mints an obligation** — the starting condition |
| `steps` | no | nested; each child resolves as a link |
| `end` | no | **mints an obligation** — the observable outcome |
| `verify` | no | a check |
| `fixture` | no | a fixture: arranges the state a claim is proved against |
| `tests` | no | resolves as a link — the test files covering this flow |

`start:` and `end:` are the flow's claims, and the pair is what makes a flow provable: the
walk is only worth recording if there is a state it begins in and a state it ends in that a
scenario can assert.

`tests:` is not an obligation and not evidence. Its one reader is the regression node, which
attributes a failing suite test back to the node that owns it — that reader needs a *path* and
can do nothing with an observation. That is why it split from `verify:` rather than sharing it.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

None. The `steps:` chain is the body.

## Relationships

Each child of `steps:` links to the node that performs it — an interaction, an invocation, an
endpoint. `ostler graph` is the structural authority for what a flow reaches.

## Minimal example

```bash
timeout 30 ostler scaffold flow shorten-and-follow --service acme
```

```markdown
---
type: flow
---

# Shorten and Follow

- start: a signed-in editor with no links
- steps:
  - [create-link](../http/links-api.md#create-link)
  - [follow-link](../http/links-api.md#follow-link)
- end: the browser lands on the original URL
- verify: created(subject="a link row for the submitted URL")
- verify: http_status(code=302, path="/{slug}")
- tests: tests/e2e/shorten_test.go
```

## Doctor codes it can trip

`unresolved-relation` on a `steps:` child, `undeclared-obligation` when `start:`/`end:` are
stated with no check, `weak-check`, `compound-normative-bullet`,
`overlong-normative-bullet`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The chain states the path. If a reader could follow the wrong path — a legacy flow and its
replacement, each right in its own context — and still satisfy every claim on it, that belongs
in a [`concept`](concept.md), pointed at with `detail:`.
