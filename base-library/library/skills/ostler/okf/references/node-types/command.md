# `command`

One subcommand of a [`cli`](cli.md): what a person types and what happens when they do.

## Identity

Section type. A `### <id>` under a `## Commands` heading in a `cli` file. Its id is
`path#anchor`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `usage` | no | the invocation line |
| `parent` | no | link — the parent command, for subcommand trees |
| `flags` | no | the flags it accepts |
| `args` | no | the positional arguments |
| `does` | no | nested; **mints an obligation** per value |
| `errors` | no | **mints an obligation** — what it prints on refusal |
| `exits` | no | **mints an obligation** — the code it leaves with |
| `run` | no | a performed act (repeatable) — one concrete invocation |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `capture` | no | a capture |

`errors:` and `exits:` are the refusal arm of a command, as an endpoint's `errors:`/`status:`
are of a route. Both were graded before they were declared here.

**`usage:`/`flags:`/`args:` are prose, not an invocation.** They describe *every* way to call
the command — `shortener create <url> [--slug SLUG]` is a synopsis, not any one call of it —
so they cannot compile to a scenario: there is no single argv in a sentence with `<url>` and
`[--slug SLUG]` still in it. `run:` is the concrete counterpart: one literal invocation per
value, an act (`ostler.acts`'s `invoke`, `- run: invoke(argv=["shortener", "create",
"https://example.com"])`) rather than a fixture name, bound to the `exits:`/`verify:` claim
above it by the same document-order rule `verify:`/`fixture:`/`capture:` already bind by (see
[bullet-grammar.md](../bullet-grammar.md)). A claim checked with `exits:`/`verify:` and no
`run:` above it compiles to nothing — QA's compiler gaps it as `uncompilable-claim` and doctor
raises `unbound-command-claim` on the book itself, before a plan is ever compiled.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Relationships

`parent:` builds subcommand trees. `detail:` is the key that points at a `concept` — use it
when two commands do the same job in different contexts.

## Minimal example

```bash
timeout 30 ostler scaffold command create --in docs/features/acme/shortener-cli.md
```

```markdown
### create

- usage: shortener create <url> [--slug SLUG]
- flags: --slug — request a specific slug
- args: url — the URL to shorten
- does: mints a short link for the given URL
- does: prints the resulting short URL on stdout
- errors: prints "slug already in use" when --slug is taken
- exits: 0 on success
- run: invoke(argv=["shortener", "create", "https://example.com"])
- verify: exit_status(code=0)
- exits: 2 on a taken slug
- run: invoke(argv=["shortener", "create", "https://example.com", "--slug", "taken"])
- verify: exit_status(code=2)
- code: cmd/shortener/create.go::runCreate
```

## Doctor codes it can trip

`compound-normative-bullet`, `overlong-normative-bullet`, `undeclared-obligation`,
`weak-check`, `unparsed-check`, `unparsed-act`, `undeclared-act-locator`,
`unbound-command-claim`, `dangling-code-ref`, `missing-code-symbol`, `unresolved-relation`.
See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this command does. If a reader could pick the wrong command — a legacy one
and its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
