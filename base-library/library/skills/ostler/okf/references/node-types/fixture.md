# fixture

A named, static-checkable arrangement: a repeatable way to reach the state a claim is about,
addressable by name from a `fixture:` bullet on [`environment`](environment.md),
[`command`](command.md), [`endpoint`](endpoint.md), [`interaction`](interaction.md),
[`invocation`](invocation.md), [`method`](method.md) and [`field`](field.md). Where those seven
types' own `fixture:`/`verify:` pair is about *this one claim's* arrangement and observation, a
`fixture` node is the arrangement itself, written once and named from every claim that needs it.

## Identity

A `fixture` node is **file-level** (`kind="file"`, `context="qa/fixtures"`) — the whole file is
the node, not a `### id` heading inside one. Its id is the repo-relative path
(`docs/features/<surface>/fixtures/<name>.md`), and the name other bullets reference it by is the
file's stem: `seeded-acme.md` is named `seeded-acme`. It reuses `## Steps` for its own body — the
same section type a [`runbook`](runbook.md) uses — because "seed this, then verify it took" is the
same shape as a boot step.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `args:` | no | The parameters this fixture takes, space-separated names. A `fixture:` bullet elsewhere passes them as `name=value` pairs; passing a name not in this list is `fixture-arg-mismatch`. |
| `provides:` | no | Nested. What the fixture's last step leaves behind — the keys a `@<this-fixture>.<key>` reference on another node may read. A reference naming a key not listed here is `fixture-undeclared-provides`. |
| `needs:` | no | Nested, `link`. Another fixture this one composes on top of, referenced as a markdown link to that fixture's file. A `needs:` chain that cycles is `fixture-needs-cycle`. |
| `secrets:` | no | Nested. Environment-variable NAMES this fixture's steps read — never a value or a mint recipe. The harness resolves each from its own environment at run time; a name that is not a valid environment-variable identifier is `fixture-secret-name`, and a name absent from the harness's environment at run time is an environment fault, not a book/code defect, because the step never got to run. |

`args:` is spelled `args`, not `params` — `params` is a global relation key
(`registry.RELATION_KEYS`) already checked by `relation-without-subject`, and a fixture's own
parameter list is not a relation.

## `## Steps`

Each step under a fixture's `## Steps` carries a `kind:` narrower than a runbook step's: only
`seed`, `run`, `verify` are legal here (`fixture-step-kind`), because a fixture's job is to put
data in place and confirm it landed — not to boot a stack, which is the runbook's job.

A fixture's own steps do **not** carry `capture:`. `capture:` lives on the seven consuming
node types, where it names what a *scenario* pulled out of a live response or the DOM — a
fixture's `provides:` is the equivalent idea for what the arrangement itself leaves behind.

## Relationships

- Referenced by `fixture:` bullets on the seven node types above, by file stem.
- `needs:` links to another `fixture` node's file.
- `@<fixture>.<key>` and `$<captured-name>` are the two reference forms a route path template,
  a request-body value, a `fixture:` bullet's args, or a `verify:` call may use — parsed by
  `ostler.qa.references` and resolved statically by `compile_plan` (never executed in this pass).

## Minimal example

```bash
timeout 30 ostler scaffold fixture seeded-acme --in docs/features/acme/fixtures/
```

```markdown
---
type: fixture
title: Seeded acme
---
# Seeded acme

- args: id
- provides:
  - id — the seeded account's id

## Steps

### seed-it

- kind: seed
- run: ./scripts/seed-acme.sh
```

## Doctor codes it can trip

See [`../doctor-codes.md`](../doctor-codes.md): `unknown-book-fixture`, `fixture-step-kind`,
`fixture-arg-mismatch`, `fixture-needs-cycle`, `fixture-undeclared-provides`,
`fixture-secret-name`.

## When bullets are not enough

A fixture's own steps are shell commands and a check, the same as a runbook's — anything the
grammar cannot express (branching setup, environment-specific seeding) belongs in the script
`run:` names, not encoded into more bullets.
