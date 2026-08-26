# `cli`

A command-line binary: the surface a person or a script drives from a shell. Reach for `cli`
for the executable itself; each subcommand is a [`command`](command.md) node under this file's
`## Commands`.

Not a CLI: a bounded shell command that a runbook runs to boot a stack — that is a
[`step`](step.md). A `cli` node is a product surface someone invokes directly.

## Identity

File type with **no context folder** (`context=""`): it lives under
`docs/features/<service>/` directly rather than in a subtree, with `type: cli` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `binary` | no | the executable name as invoked |
| `code` | no | resolves as a link, and **owns** its file — `path::symbol` |

`binary:` deliberately does not own: naming an executable is not grounding it. `code:` is what
makes `qa context` attribute a change under that path to this node.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

`## Commands` — required, and required to be non-empty. A CLI that exposes no command is not
one.

## Relationships

A [`runbook`](runbook.md) points at this node with `cli:` when it drives the stack through this
binary. Subcommands nest under a parent command with `parent:`.

## Minimal example

```bash
timeout 30 ostler scaffold cli shortener-cli --service acme
```

```markdown
---
type: cli
---

# shortener

- binary: shortener
- code: cmd/shortener/main.go::main

## Commands

### create

- usage: shortener create <url> [--slug SLUG]
- does: mints a short link for the given URL
- code: cmd/shortener/create.go::runCreate
- verify: exit_status(code=0)
```

## Doctor codes it can trip

`missing-required-section`, `empty-required-section`, `dangling-code-ref`,
`missing-code-symbol`, plus whatever its `command` children trip. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this binary is. If a reader could pick the wrong CLI — a legacy one and its
replacement, each right in its own context — and still satisfy every claim on it, that belongs
in a [`concept`](concept.md), pointed at with `detail:`.
