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
| `code` | no | link, **owns** its file — the implementation the flow's steps walk through |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | arranges the world the walk starts in — or `none, because ...` |
| `tests` | no | resolves as a link — the test files covering this flow |

`start:` and `end:` are the flow's claims, and the pair is what makes a flow provable: the
walk is only worth recording if there is a state it begins in and a state it ends in that a
scenario can assert.

On a `cli`, `start:` is observed before the first step, in the working directory the walk
begins in. No command has run at that moment, so its `verify:` is
`absent(subject="<file>")` on the exact relative path of a file the walk goes on to create.
A check that reads a command's output, or that compares the directory either side of a run,
has nothing to read there, and the compiler refuses it as `uncompilable-claim`. A starting
world that holds files is stated on `fixture:` instead.

`end:` spans the whole walk. A check on it that compares the directory either side, such as
`unchanged`, `created` or `removed`, reads the directory before the first step and again after
the last. So `end: unchanged(subject="<file>")` claims the walk as a whole left that file as
it found it. On a walk whose `start:` says the file is absent and whose first step creates
it, that claim is false for a correct app. A claim about one step, such as a preview that
writes nothing, is not the flow's claim. It goes on the command or invocation that step links
to, with a `fixture:` that puts the file in place and `verify: unchanged(subject="<file>")`.
The flow's `end:` then states what the whole walk leaves behind.

A flow's claims are about the world its steps left behind, and that world is the world they
started in plus the walk — so the starting world is part of the claim, and the flow states it.
`- fixture: <name> [args] — <state it leaves>` arranges it before the first step. A flow whose
claims hold in whatever world it finds says so with a reason: `- fixture: none, because the
first step creates everything the last step observes`. A flow that states neither is
`unarranged-journey`, and no scenario is compiled for it — a walk run against whatever the
previous scenario happened to leave asserts `end:` against accidental state, and the red it
produces is evidence about the run order, not about the service. A bare `- fixture:` or a bare
`- fixture: none` is the undecided case, not the second answer.

`tests:` is not an obligation and not evidence. Its one reader is the regression node, which
attributes a failing suite test back to the node that owns it — that reader needs a *path* and
can do nothing with an observation. That is why it split from `verify:` rather than sharing it.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

None. The `steps:` chain is the body.

## Relationships

Each child of `steps:` links to the node that performs it — an interaction, an invocation, an
endpoint. `ostler graph` is the structural authority for what a flow reaches.

**A journey whose steps cross targets is legal, and today it compiles to nothing.** A step's
target is its node type paired with the `driver:` of the surface it lives on, so a flow that
walks a mobile app and then a web app — or drives an api and then a browser — names two. One
compiled scenario binds one driver to one service, so there is no shape for that journey yet,
and the compiler says so with `needs-multi-target-runtime` rather than asking anyone to change
the book. **That is not a defect in the flow.** Write the
journey the user actually performs; a journey that is really two, performed by two people or
two sittings, is two flows, and splitting it to make the compiler happy records a walk nobody
takes.

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
- verify: count(subject="links owned by the signed-in editor", equals=0)
- steps:
  - [create-link](../http/links-api.md#create-link)
  - [follow-link](../http/links-api.md#follow-link)
- end: the browser lands on the original URL
- verify: http_status(code=302, path="/{slug}")
- tests: tests/e2e/shorten_test.go
```

## Doctor codes it can trip

`unresolved-relation` on a `steps:` child, `undeclared-obligation` when `start:`/`end:` are
stated with no check, `unarranged-journey` when the flow neither arranges a world nor says it
needs none, `weak-check`, `compound-normative-bullet`, `overlong-normative-bullet`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The chain states the path. If a reader could follow the wrong path — a legacy flow and its
replacement, each right in its own context — and still satisfy every claim on it, that belongs
in a [`concept`](concept.md), pointed at with `detail:`.
